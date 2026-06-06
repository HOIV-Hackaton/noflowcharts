from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import socket
import time
from typing import Any

import paramiko

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, SshError
from app.core.redaction import redact_text
from app.schemas.phoenix import SystemInfo


MAX_STREAM_CHARS = 32 * 1024


@dataclass(frozen=True)
class SshCommandResult:
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class SshRunner:
    def __init__(
        self,
        settings: Settings | None = None,
        client_factory: Callable[[], Any] | None = None,
        connect_timeout: float = 10.0,
        command_timeout: float = 30.0,
    ):
        self.settings = settings or get_settings()
        self.client_factory = client_factory or paramiko.SSHClient
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout

    def run(self, system: SystemInfo, command: str) -> SshCommandResult:
        key_path = self._private_key_path()
        username = system.username or self.settings.ssh_username
        if not username:
            raise ConfigurationError("Missing SSH username from Phoenix system and SSH_USERNAME fallback")

        client = self.client_factory()
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
            _, stdout, stderr = client.exec_command(command, timeout=self.command_timeout)
            exit_code = self._wait_for_exit(stdout.channel)
            if exit_code is None:
                return SshCommandResult(command=command, exit_code=None, stdout="", stderr="Command timed out", timed_out=True)
            return SshCommandResult(
                command=command,
                exit_code=exit_code,
                stdout=_truncate(_decode_stream(stdout)),
                stderr=_truncate(_decode_stream(stderr)),
                timed_out=False,
            )
        except (TimeoutError, socket.timeout):
            return SshCommandResult(command=command, exit_code=None, stdout="", stderr="Command timed out", timed_out=True)
        except Exception as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            raise SshError(f"SSH command failed: {message}") from exc
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

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

    def _wait_for_exit(self, channel: Any) -> int | None:
        exit_status_ready = getattr(channel, "exit_status_ready", None)
        if not callable(exit_status_ready):
            return channel.recv_exit_status()

        deadline = time.monotonic() + self.command_timeout
        while time.monotonic() < deadline:
            if exit_status_ready():
                return channel.recv_exit_status()
            time.sleep(0.1)

        close = getattr(channel, "close", None)
        if callable(close):
            close()
        return None


def _decode_stream(stream: Any) -> str:
    data = stream.read()
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _truncate(value: str) -> str:
    if len(value) <= MAX_STREAM_CHARS:
        return value
    return value[:MAX_STREAM_CHARS] + "\n[truncated]"
