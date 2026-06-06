from pathlib import Path
import socket

import pytest
from paramiko.ssh_exception import AuthenticationException

from app.core.config import Settings
from app.core.errors import ConfigurationError, SshError
from app.schemas.phoenix import SystemInfo
from app.services.ssh_keys import candidate_private_key_paths
from app.services.ssh_runner import MAX_STREAM_CHARS, SshRunner
from app.services.terminal_session import SshPtySession


class FakeChannel:
    def __init__(self, exit_code=0):
        self.exit_code = exit_code
        self.closed = False

    def exit_status_ready(self):
        return True

    def recv_exit_status(self):
        return self.exit_code

    def close(self):
        self.closed = True


class FakeStream:
    def __init__(self, data, exit_code=0):
        self.data = data
        self.channel = FakeChannel(exit_code)

    def read(self):
        return self.data


class FakeSshClient:
    def __init__(self):
        self.connected = False
        self.closed = False
        self.command = None

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, **kwargs):
        self.connected = True
        self.connect_kwargs = kwargs

    def exec_command(self, command, timeout):
        self.command = command
        stdout = FakeStream(("x" * (MAX_STREAM_CHARS + 10)).encode(), exit_code=0)
        stderr = FakeStream(b"")
        return None, stdout, stderr

    def close(self):
        self.closed = True


class FakeInteractiveChannel:
    def __init__(self):
        self.closed = False
        self.timeout = None

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv_ready(self):
        return False

    def recv(self, max_bytes):
        return b""

    def send(self, data):
        self.sent = data

    def close(self):
        self.closed = True


class FakeTransport:
    def __init__(self):
        self.keepalive = None

    def set_keepalive(self, seconds):
        self.keepalive = seconds


class FakePtySshClient:
    def __init__(self, should_fail_auth=False):
        self.should_fail_auth = should_fail_auth
        self.closed = False
        self.channel = FakeInteractiveChannel()
        self.transport = FakeTransport()

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, **kwargs):
        self.connect_kwargs = kwargs
        if self.should_fail_auth:
            raise AuthenticationException("bad key")

    def get_transport(self):
        return self.transport

    def invoke_shell(self, **kwargs):
        self.shell_kwargs = kwargs
        return self.channel

    def close(self):
        self.closed = True


def test_ssh_runner_executes_single_command_and_truncates_output(tmp_path, monkeypatch):
    key_path = tmp_path / "key.pem"
    key_path.write_text("fake", encoding="utf-8")
    fake_client = FakeSshClient()
    settings = Settings(ssh_private_key_path=str(key_path))
    runner = SshRunner(settings=settings, client_factory=lambda: fake_client)
    monkeypatch.setattr(runner, "_load_private_key", lambda path: "key")

    result = runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "systemctl status nginx")

    assert fake_client.connected is True
    assert fake_client.closed is True
    assert fake_client.connect_kwargs["hostname"] == "10.0.0.5"
    assert fake_client.command == "systemctl status nginx"
    assert result.exit_code == 0
    assert len(result.stdout) > MAX_STREAM_CHARS
    assert result.stdout.endswith("[truncated]")


def test_candidate_private_key_paths_use_configured_key_first_then_sibling_pems(tmp_path):
    other_key = tmp_path / "case1_key.pem"
    configured_key = tmp_path / "case2_key.pem"
    third_key = tmp_path / "case3_key.pem"
    ignored_file = tmp_path / "notes.txt"
    for path in (other_key, configured_key, third_key, ignored_file):
        path.write_text("fake", encoding="utf-8")

    paths = candidate_private_key_paths(Settings(_env_file=None, ssh_private_key_path=str(configured_key)))

    assert paths == [configured_key, other_key, third_key]


def test_candidate_private_key_paths_keeps_inaccessible_configured_key_and_sibling_fallbacks(tmp_path, monkeypatch):
    configured_key = tmp_path / "case1_key.pem"
    fallback_key = tmp_path / "case2_key.pem"
    configured_key.write_text("fake", encoding="utf-8")
    fallback_key.write_text("fake", encoding="utf-8")
    original_exists = Path.exists

    def fake_exists(path):
        if path == configured_key:
            raise PermissionError("permission denied")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    paths = candidate_private_key_paths(Settings(_env_file=None, ssh_private_key_path=str(configured_key)))

    assert paths == [configured_key, fallback_key]


def test_ssh_runner_tries_sibling_key_after_auth_failure(tmp_path, monkeypatch):
    primary_key = tmp_path / "case1_key.pem"
    fallback_key = tmp_path / "case2_key.pem"
    primary_key.write_text("fake", encoding="utf-8")
    fallback_key.write_text("fake", encoding="utf-8")

    created_clients = []

    def client_factory():
        client = FakeSshClient()
        original_connect = client.connect

        def connect(**kwargs):
            client.connect_kwargs = kwargs
            if len(created_clients) == 1:
                raise AuthenticationException("bad key")
            original_connect(**kwargs)

        client.connect = connect
        created_clients.append(client)
        return client

    runner = SshRunner(
        settings=Settings(_env_file=None, ssh_private_key_path=str(primary_key)),
        client_factory=client_factory,
    )
    monkeypatch.setattr(runner, "_load_private_key", lambda path: f"key:{path.name}")

    result = runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "uptime")

    assert len(created_clients) == 2
    assert created_clients[0].closed is True
    assert created_clients[1].closed is True
    assert created_clients[0].connect_kwargs["pkey"] == "key:case1_key.pem"
    assert created_clients[1].connect_kwargs["pkey"] == "key:case2_key.pem"
    assert created_clients[1].command == "uptime"
    assert result.exit_code == 0


def test_ssh_pty_session_tries_sibling_key_after_auth_failure(tmp_path, monkeypatch):
    primary_key = tmp_path / "case1_key.pem"
    fallback_key = tmp_path / "case2_key.pem"
    primary_key.write_text("fake", encoding="utf-8")
    fallback_key.write_text("fake", encoding="utf-8")
    created_clients = []

    def client_factory():
        client = FakePtySshClient(should_fail_auth=len(created_clients) == 0)
        created_clients.append(client)
        return client

    session = SshPtySession(
        SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"),
        settings=Settings(_env_file=None, ssh_private_key_path=str(primary_key)),
        client_factory=client_factory,
    )
    monkeypatch.setattr(session, "_load_private_key", lambda path: f"key:{path.name}")

    session.open()

    assert len(created_clients) == 2
    assert created_clients[0].closed is True
    assert created_clients[1].connect_kwargs["pkey"] == "key:case2_key.pem"
    assert created_clients[1].transport.keepalive == 30
    assert created_clients[1].shell_kwargs == {"term": "xterm-256color", "width": 120, "height": 32}
    assert session.client is created_clients[1]
    assert session.channel is created_clients[1].channel
    assert session.channel.timeout == 0.0


def test_ssh_runner_requires_private_key_path():
    runner = SshRunner(settings=Settings(_env_file=None, ssh_private_key_path=None))

    with pytest.raises(Exception) as exc:
        runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "uptime")

    assert "SSH_PRIVATE_KEY_PATH" in str(exc.value)


def test_ssh_runner_reports_command_timeout(tmp_path, monkeypatch):
    key_path = tmp_path / "key.pem"
    key_path.write_text("fake", encoding="utf-8")

    class TimeoutClient(FakeSshClient):
        def exec_command(self, command, timeout):
            raise socket.timeout("timed out")

    runner = SshRunner(settings=Settings(_env_file=None, ssh_private_key_path=str(key_path)), client_factory=TimeoutClient)
    monkeypatch.setattr(runner, "_load_private_key", lambda path: "key")

    result = runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "sleep 99")

    assert result.timed_out is True
    assert result.exit_code is None


def test_ssh_runner_times_out_when_channel_never_finishes(tmp_path, monkeypatch):
    key_path = tmp_path / "key.pem"
    key_path.write_text("fake", encoding="utf-8")

    class HangingChannel(FakeChannel):
        def exit_status_ready(self):
            return False

    class HangingClient(FakeSshClient):
        def __init__(self):
            super().__init__()
            self.channel = HangingChannel()

        def exec_command(self, command, timeout):
            self.command = command
            stdout = FakeStream(b"", exit_code=0)
            stdout.channel = self.channel
            stderr = FakeStream(b"")
            return None, stdout, stderr

    client = HangingClient()
    runner = SshRunner(
        settings=Settings(_env_file=None, ssh_private_key_path=str(key_path)),
        client_factory=lambda: client,
        command_timeout=0.01,
    )
    monkeypatch.setattr(runner, "_load_private_key", lambda path: "key")

    result = runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "sleep 99")

    assert result.timed_out is True
    assert result.exit_code is None
    assert client.channel.closed is True


def test_ssh_errors_are_redacted(tmp_path, monkeypatch):
    key_path = tmp_path / "key.pem"
    key_path.write_text("fake", encoding="utf-8")

    class FailingClient(FakeSshClient):
        def connect(self, **kwargs):
            raise RuntimeError("bad secret-token")

    settings = Settings(_env_file=None, ssh_private_key_path=str(key_path), phoenix_api_token="secret-token")
    runner = SshRunner(settings=settings, client_factory=FailingClient)
    monkeypatch.setattr(runner, "_load_private_key", lambda path: "key")

    with pytest.raises(SshError) as exc_info:
        runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "uptime")

    assert "secret-token" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_phoenix_username_preferred_and_env_fallback_used_only_when_missing(tmp_path, monkeypatch):
    key_path = tmp_path / "key.pem"
    key_path.write_text("fake", encoding="utf-8")
    fake_client = FakeSshClient()
    runner = SshRunner(
        settings=Settings(_env_file=None, ssh_private_key_path=str(key_path), ssh_username="fallback"),
        client_factory=lambda: fake_client,
    )
    monkeypatch.setattr(runner, "_load_private_key", lambda path: "key")

    runner.run(SystemInfo(ip="10.0.0.5", port=22, username="phoenix", os="Ubuntu"), "uptime")
    assert fake_client.connect_kwargs["username"] == "phoenix"

    runner.run(SystemInfo(ip="10.0.0.5", port=22, username="", os="Ubuntu"), "uptime")
    assert fake_client.connect_kwargs["username"] == "fallback"


def test_ssh_runner_requires_existing_key_and_username(tmp_path):
    missing_key = tmp_path / "missing.pem"
    runner = SshRunner(settings=Settings(_env_file=None, ssh_private_key_path=str(missing_key)))
    with pytest.raises(ConfigurationError):
        runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "uptime")

    key_path = tmp_path / "key.pem"
    key_path.write_text("fake", encoding="utf-8")
    runner = SshRunner(settings=Settings(_env_file=None, ssh_private_key_path=str(key_path), ssh_username=None))
    with pytest.raises(ConfigurationError):
        runner.run(SystemInfo(ip="10.0.0.5", port=22, username="", os="Ubuntu"), "uptime")
