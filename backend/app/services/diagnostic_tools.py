from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.redaction import redact_text
from app.schemas.phoenix import SystemInfo
from app.services.diagnostic_policy import build_diagnostic_command, redact_diagnostic_output
from app.services.ssh_runner import SshCommandResult, SshRunner


@dataclass(frozen=True)
class DiagnosticResult:
    tool: str
    arguments: dict[str, Any]
    command: str
    rule_id: str
    reason: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class DiagnosticToolbox:
    def __init__(self, ssh_runner: SshRunner | None = None):
        self.ssh_runner = ssh_runner or SshRunner()

    def run(self, system: SystemInfo, tool: str, arguments: dict[str, Any] | None = None) -> DiagnosticResult:
        safe = build_diagnostic_command(tool, arguments)
        result: SshCommandResult = self.ssh_runner.run(system, safe.command)
        secrets = get_settings().configured_secrets()
        stdout = redact_diagnostic_output(redact_text(result.stdout, secrets))
        stderr = redact_diagnostic_output(redact_text(result.stderr, secrets))
        return DiagnosticResult(
            tool=tool,
            arguments=arguments or {},
            command=safe.command,
            rule_id=safe.rule_id,
            reason=safe.reason,
            exit_code=result.exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=result.timed_out,
        )
