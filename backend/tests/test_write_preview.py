from app.schemas.phoenix import SystemInfo
from app.services.ssh_runner import SshCommandResult
from app.services.write_preview import WritePreviewer, parse_write_command


class FakePreviewRunner:
    def __init__(self, content="PORT=8080\nSECRET_TOKEN=plain-secret\n"):
        self.content = content
        self.commands = []

    def run(self, system, command):
        self.commands.append(command)
        return SshCommandResult(command=command, exit_code=0, stdout=self.content, stderr="", timed_out=False)


def system():
    return SystemInfo(ip="10.0.0.5", port=22, username="azureuser", os="Ubuntu")


def test_sed_in_place_preview_generates_redacted_unified_diff():
    runner = FakePreviewRunner()
    preview = WritePreviewer(runner, secrets=["plain-secret"]).preview(system(), "sed -i 's/8080/9090/' /etc/app.conf")

    assert preview["status"] == "available"
    assert preview["command_kind"] == "sed_i"
    assert preview["target_path"] == "/etc/app.conf"
    assert "--- a/etc/app.conf" in preview["diff"]
    assert "-PORT=8080" in preview["diff"]
    assert "+PORT=9090" in preview["diff"]
    assert "plain-secret" not in str(preview)
    assert "[REDACTED]" in preview["diff"]
    assert runner.commands == ["cat -- /etc/app.conf"]


def test_sed_in_place_preview_supports_common_sed_basic_regex():
    runner = FakePreviewRunner("127.0.0.2 partner-api.internal\n127.0.0.1 localhost\n")
    preview = WritePreviewer(runner).preview(
        system(),
        r"sudo -n sed -i 's/^127\.0\.0\.2[[:space:]]\+partner-api\.internal$/127.0.0.1 partner-api.internal/' /etc/hosts",
    )

    assert preview["status"] == "available"
    assert preview["command_kind"] == "sed_i"
    assert preview["target_path"] == "/etc/hosts"
    assert "-127.0.0.2 partner-api.internal" in preview["diff"]
    assert "+127.0.0.1 partner-api.internal" in preview["diff"]
    assert runner.commands == ["sudo -n cat -- /etc/hosts"]


def test_echo_redirect_and_append_are_previewed():
    replace = WritePreviewer(FakePreviewRunner("old\n")).preview(system(), "echo 'new value' > /tmp/example.conf")
    append = WritePreviewer(FakePreviewRunner("old\n")).preview(system(), "echo added >> /tmp/example.conf")

    assert replace["status"] == "available"
    assert "-old" in replace["diff"]
    assert "+new value" in replace["diff"]
    assert append["status"] == "available"
    assert "+added" in append["diff"]


def test_printf_redirect_and_tee_pipeline_are_previewed():
    printf_preview = WritePreviewer(FakePreviewRunner("old\n")).preview(system(), "printf 'new\\n' > /tmp/example.conf")
    tee_preview = WritePreviewer(FakePreviewRunner("old\n")).preview(system(), "echo 'new' | sudo -n tee -a /etc/example.conf")

    assert printf_preview["status"] == "available"
    assert "+new" in printf_preview["diff"]
    assert tee_preview["status"] == "available"
    assert tee_preview["command_kind"] == "tee"
    assert tee_preview["target_path"] == "/etc/example.conf"
    assert "+new" in tee_preview["diff"]


def test_unsupported_write_command_returns_unavailable_preview():
    parsed = parse_write_command("echo one > /tmp/a && echo two > /tmp/b")

    assert parsed is not None
    assert parsed.kind == "unsupported_write"
    preview = WritePreviewer(FakePreviewRunner()).preview(system(), "echo one > /tmp/a && echo two > /tmp/b")
    assert preview["status"] == "unavailable"
    assert "target file path" in preview["reason"]


def test_non_write_command_is_not_applicable_and_does_not_read_remote_file():
    runner = FakePreviewRunner()
    preview = WritePreviewer(runner).preview(system(), "systemctl status nginx")

    assert preview == {"status": "not_applicable", "redacted": True}
    assert runner.commands == []
