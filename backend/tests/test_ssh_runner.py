from pathlib import Path

import pytest

from app.core.config import Settings
from app.schemas.phoenix import SystemInfo
from app.services.ssh_runner import MAX_STREAM_CHARS, SshRunner


class FakeChannel:
    def __init__(self, exit_code=0):
        self.exit_code = exit_code

    def recv_exit_status(self):
        return self.exit_code


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


def test_ssh_runner_requires_private_key_path():
    runner = SshRunner(settings=Settings(_env_file=None, ssh_private_key_path=None))

    with pytest.raises(Exception) as exc:
        runner.run(SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu"), "uptime")

    assert "SSH_PRIVATE_KEY_PATH" in str(exc.value)
