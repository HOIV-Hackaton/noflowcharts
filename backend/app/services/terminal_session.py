import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread
from typing import Any

import paramiko
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ConfigurationError, SshError
from app.core.redaction import redact_text
from app.schemas.phoenix import SystemInfo


class TerminalSession:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: Any | None = None,
        connect_timeout: float = 10.0,
    ):
        self.settings = settings or get_settings()
        self.client_factory = client_factory or paramiko.SSHClient
        self.connect_timeout = connect_timeout

    async def bridge(self, websocket: WebSocket, system: SystemInfo, cols: int = 120, rows: int = 32) -> None:
        await websocket.accept()
        client = self.client_factory()
        channel = None
        stop_event = Event()
        output_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        try:
            await websocket.send_json({"type": "status", "message": "Opening SSH terminal..."})
            channel = await asyncio.to_thread(self._open_channel, client, system, cols, rows)
            await websocket.send_json({"type": "status", "message": "Remote terminal connected."})

            reader = Thread(
                daemon=True,
                target=self._read_channel,
                args=(channel, output_queue, loop, stop_event),
            )
            reader.start()

            await asyncio.gather(
                self._send_output(websocket, output_queue),
                self._receive_input(websocket, channel),
            )
        except WebSocketDisconnect:
            pass
        except AppError as exc:
            await websocket.send_json({"type": "error", "message": exc.message})
        except Exception as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            await websocket.send_json({"type": "error", "message": f"Terminal session failed: {message}"})
        finally:
            stop_event.set()
            if channel is not None:
                channel.close()
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def _open_channel(self, client: Any, system: SystemInfo, cols: int, rows: int):
        key_path = self._private_key_path()
        username = system.username or self.settings.ssh_username
        if not username:
            raise ConfigurationError("Missing SSH username from Phoenix system and SSH_USERNAME fallback")

        try:
            if hasattr(client, "set_missing_host_key_policy"):
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            key = self._load_private_key(key_path)
            client.connect(
                hostname=system.ip,
                port=system.port,
                username=username,
                pkey=key,
                timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            transport = client.get_transport()
            if transport is None:
                raise SshError("SSH transport was not established")
            channel = transport.open_session()
            channel.get_pty(term="xterm-256color", width=cols, height=rows)
            channel.invoke_shell()
            return channel
        except AppError:
            raise
        except Exception as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            raise SshError(f"SSH terminal failed: {message}") from exc

    async def _receive_input(self, websocket: WebSocket, channel: Any) -> None:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")

            if message_type == "input":
                data = message.get("data")
                if isinstance(data, str):
                    channel.send(data)
            elif message_type == "resize":
                cols = _bounded_int(message.get("cols"), minimum=20, maximum=400, fallback=120)
                rows = _bounded_int(message.get("rows"), minimum=8, maximum=120, fallback=32)
                channel.resize_pty(width=cols, height=rows)

    async def _send_output(self, websocket: WebSocket, output_queue: asyncio.Queue[dict[str, str]]) -> None:
        while True:
            message = await output_queue.get()
            if message.get("type") == "close":
                await websocket.send_json({"type": "status", "message": message.get("message", "Remote terminal disconnected.")})
                await websocket.close()
                return
            await websocket.send_json(message)

    def _read_channel(
        self,
        channel: Any,
        output_queue: asyncio.Queue[dict[str, str]],
        loop: asyncio.AbstractEventLoop,
        stop_event: Event,
    ) -> None:
        while not stop_event.is_set():
            try:
                if channel.recv_ready():
                    data = channel.recv(4096).decode("utf-8", errors="replace")
                    loop.call_soon_threadsafe(output_queue.put_nowait, {"type": "output", "data": data})
                elif channel.closed or channel.exit_status_ready():
                    loop.call_soon_threadsafe(
                        output_queue.put_nowait,
                        {"type": "close", "message": "Remote terminal disconnected."},
                    )
                    return
                else:
                    stop_event.wait(0.03)
            except Exception as exc:
                message = redact_text(str(exc), self.settings.configured_secrets())
                loop.call_soon_threadsafe(
                    output_queue.put_nowait,
                    {"type": "error", "message": f"Terminal read failed: {message}"},
                )
                return

    def _private_key_path(self) -> Path:
        try:
            self.settings.require_ssh_key()
        except RuntimeError as exc:
            raise ConfigurationError(str(exc)) from exc
        assert self.settings.ssh_private_key_path is not None
        path = Path(self.settings.ssh_private_key_path).expanduser()
        if not path.exists():
            raise ConfigurationError("Configured SSH private key path does not exist")
        return path

    def _load_private_key(self, path: Path) -> paramiko.PKey:
        loaders = (
            paramiko.Ed25519Key.from_private_key_file,
            paramiko.RSAKey.from_private_key_file,
            paramiko.ECDSAKey.from_private_key_file,
        )
        last_error: Exception | None = None
        for loader in loaders:
            try:
                return loader(str(path))
            except Exception as exc:
                last_error = exc
        raise ConfigurationError(f"Could not load SSH private key: {last_error}")


class SshPtySession:
    def __init__(
        self,
        system: SystemInfo,
        settings: Settings | None = None,
        client_factory: Callable[[], Any] | None = None,
        connect_timeout: float = 10.0,
        term: str = "xterm-256color",
        cols: int = 120,
        rows: int = 32,
    ):
        self.system = system
        self.settings = settings or get_settings()
        self.client_factory = client_factory or paramiko.SSHClient
        self.connect_timeout = connect_timeout
        self.term = term
        self.cols = cols
        self.rows = rows
        self.client: Any | None = None
        self.channel: Any | None = None

    def open(self) -> None:
        key_path = self._private_key_path()
        username = self.system.username or self.settings.ssh_username
        if not username:
            raise ConfigurationError("Missing SSH username from Phoenix system and SSH_USERNAME fallback")

        client = self.client_factory()
        try:
            if hasattr(client, "set_missing_host_key_policy"):
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            key = self._load_private_key(key_path)
            client.connect(
                hostname=self.system.ip,
                port=self.system.port,
                username=username,
                pkey=key,
                timeout=self.connect_timeout,
                banner_timeout=self.connect_timeout,
                auth_timeout=self.connect_timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            transport = getattr(client, "get_transport", lambda: None)()
            if transport is not None and hasattr(transport, "set_keepalive"):
                transport.set_keepalive(30)
            self.channel = client.invoke_shell(term=self.term, width=self.cols, height=self.rows)
            if hasattr(self.channel, "settimeout"):
                self.channel.settimeout(0.0)
            self.client = client
        except Exception as exc:
            close = getattr(client, "close", None)
            if callable(close):
                close()
            message = redact_text(str(exc), self.settings.configured_secrets())
            raise SshError(f"SSH terminal failed: {message}") from exc

    def read_available(self, max_bytes: int = 4096) -> str:
        if self.channel is None:
            return ""
        recv_ready = getattr(self.channel, "recv_ready", None)
        if callable(recv_ready) and not recv_ready():
            return ""
        try:
            data = self.channel.recv(max_bytes)
        except Exception:
            return ""
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)

    def write(self, data: str) -> None:
        if self.channel is None:
            raise SshError("SSH terminal is not open")
        self.channel.send(data)

    def resize(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        if self.channel is not None and hasattr(self.channel, "resize_pty"):
            self.channel.resize_pty(width=cols, height=rows)

    def is_closed(self) -> bool:
        if self.channel is None:
            return True
        closed = getattr(self.channel, "closed", False)
        if closed:
            return True
        exit_status_ready = getattr(self.channel, "exit_status_ready", None)
        return bool(callable(exit_status_ready) and exit_status_ready())

    def close(self) -> None:
        for obj in (self.channel, self.client):
            close = getattr(obj, "close", None)
            if callable(close):
                close()
        self.channel = None
        self.client = None

    def _private_key_path(self) -> Path:
        try:
            self.settings.require_ssh_key()
        except RuntimeError as exc:
            raise ConfigurationError(str(exc)) from exc
        assert self.settings.ssh_private_key_path is not None
        path = Path(self.settings.ssh_private_key_path).expanduser()
        if not path.exists():
            raise ConfigurationError("Configured SSH private key path does not exist")
        return path

    def _load_private_key(self, path: Path) -> paramiko.PKey:
        loaders = (paramiko.Ed25519Key.from_private_key_file, paramiko.RSAKey.from_private_key_file, paramiko.ECDSAKey.from_private_key_file)
        last_error: Exception | None = None
        for loader in loaders:
            try:
                return loader(str(path))
            except Exception as exc:
                last_error = exc
        raise ConfigurationError(f"Could not load SSH private key: {last_error}")


def _bounded_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    if not isinstance(value, int):
        return fallback
    return max(minimum, min(maximum, value))


def monotonic_seconds() -> float:
    return time.monotonic()
