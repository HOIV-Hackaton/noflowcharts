from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agent.providers import LlmProvider, complete_json_with_metrics, get_llm_provider
from app.core.config import get_settings
from app.core.errors import AgentError
from app.core.redaction import redact_payload
from app.schemas.runs import CommandClassification


class CommandProposal(BaseModel):
    intent: str = Field(min_length=1)
    command: str = Field(min_length=1)
    expected_signal: str = Field(min_length=1)
    risk_level: str | None = None
    command_class_hint: CommandClassification | None = None
    rollback_note: str | None = None
    phase: str | None = None
    evidence_basis: str | None = None
    evidence_gap: str | None = None

    @field_validator("command_class_hint", mode="before")
    @classmethod
    def ignore_invalid_command_class_hint(cls, value: Any) -> Any:
        if value is None or value in {item.value for item in CommandClassification}:
            return value
        return None


class DiagnosticToolProposal(BaseModel):
    mode: str = Field(pattern="^(diagnostic_tool|command_proposal)$")
    intent: str = Field(min_length=1)
    expected_signal: str = Field(min_length=1)
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    command: str | None = None
    risk_level: str | None = None
    rollback_note: str | None = None
    evidence_basis: str | None = None
    evidence_gap: str | None = None


PLANNER_SYSTEM_PROMPT = """You are the backend troubleshooting planner for an AI-assisted service desk.

Your job is to propose exactly one Ubuntu shell command for a human technician to review. The backend will enforce approval and safety checks; you must still avoid unsafe or low-value commands.

Primary objective: solve hidden Linux service incidents accurately and safely. Optimize for correct root cause, a working customer-facing fix, persistence after restart/reboot when relevant, no regression/data loss, and useful activity documentation.

Operating rules:
- Do not assume context. Use only the ticket, customer system, observations, and safety policy supplied in the user message.
- Diagnose before fixing. When uncertain, choose a read-only diagnostic command that tests the most likely hypothesis or narrows the search space.
- Be very conservative with mutation. Propose a fix only after observations support a concrete technical cause.
- Do not repeat a command when recent observations already contain its answer; use those observations to choose the next smallest diagnostic or fix.
- Treat successful empty output from filters/listener checks as a real negative finding. Do not re-run an equivalent probe just because it printed nothing.
- Before proposing, compare the candidate command against recent_observations and anti_loop_context. The next command must test a new hypothesis, inspect a newly discovered concrete resource, apply an evidence-backed fix, or validate a completed fix.
- Propose the smallest targeted command that advances the investigation or fix. Avoid compound shell, pipes, sudo, package installs, broad file edits, broad restarts, and blanket permission changes unless clearly necessary.
- For the first command, or whenever recent observations do not identify a concrete service/config/path, the command must be read-only, must not use sudo, and must not use shell control operators.
- The command string must be a single simple command. Do not use &&, ||, ;, pipes, command substitution, newlines, or fallback chains.
- Prefer read-only commands without sudo when they provide enough evidence. Use sudo -n only for targeted privileged commands that truly need it, so commands fail fast instead of prompting.
- Never propose commands that read secrets, dump environment files, delete customer data, clear logs/history, disable firewall/audit/security controls, reinitialize databases, or work around permissions by running services as root.
- Prefer service-local and app-local checks: service status, recent logs, listening ports, config syntax, disk space, permissions on the exact affected path, and health endpoints inferred from evidence.
- If the ticket names an explicit customer-facing health URL, validate that URL directly with curl --max-time 5 -fsS before lower-level listener checks.
- If a ticket provides a public validation command or script, run it only after the direct health check or fix evidence indicates the system is likely healthy; do not substitute generic diagnostics for the required validation.
- For Linux service incidents, first check the expected listener, then inspect the relevant systemd unit with systemctl cat, enabled/active state, and recent journal logs.
- If observations reveal a concrete candidate unit, process, config path, mount, port, or application directory, pivot to that resource before doing more broad discovery or repeating health/listener checks.
- Use non-interactive systemd commands. Include --no-pager for systemctl status, list-units, and list-unit-files.
- If an EnvironmentFile is involved, inspect only relevant non-secret keys like PORT or HOST rather than dumping the full file.
- If a service is disabled, enable it separately from starting it. If a config value is wrong, make the smallest targeted edit and then restart only the affected service.
- After a fix, propose validation that proves customer benefit is restored. When safe and proportionate, validate persistence with a relevant service restart, config check, or enabled-state check before activity creation.
- For final validation after a fix, prefer read-only checks and, when safe and proportionate, evidence that the fix persists after a relevant service restart or equivalent configuration check.
- Use bounded HTTP validation such as curl --max-time 5 -fsS. Run provided public validation scripts only after direct evidence indicates the fix is likely correct.
- If the previous command failed or was blocked, explain that in intent and propose the safest next diagnostic or safer alternative. Do not repeat the same failed command unless retrying is clearly justified.
- If the technician rejects a proposal or gives guidance, follow that guidance as context for the next proposal; do not interpret technician guidance as shell input.
- Related ticket context, when supplied, is historical assistance only. Do not assume the current ticket has the same root cause. Do not copy historical commands blindly. Use related root causes, validation results, and exact historical commands only to choose better diagnostics for the current system.
- Even with related ticket context, the first command must remain a read-only diagnostic unless current observations already prove a concrete fix is appropriate.

Return JSON only with keys: intent, command, expected_signal, risk_level, command_class_hint, rollback_note, phase, evidence_basis, evidence_gap.

Field guidance:
- intent: one technician-readable sentence explaining why this exact command is the next best step.
- command: one shell command only.
- expected_signal: what output or exit status would confirm or disprove the current hypothesis.
- risk_level: low, medium, or high.
- command_class_hint: read_only, mutating, risky_mutating, or blocked.
- rollback_note: required for mutating/risky commands; otherwise null.
- phase: diagnose, fix, validate, or recover.
- evidence_basis: specific observation(s) that justify this command, or "ticket symptom only" if none exist yet.
- evidence_gap: what is still unknown after this command, or null if the command should close the loop.
"""


DIAGNOSTIC_TOOL_SYSTEM_PROMPT = """You are the safe auto-diagnosis planner for an AI-assisted service desk.

You may request exactly one backend diagnostic tool call, or stop auto-diagnosis by proposing one human-approved command. The backend validates every tool argument and will reject unsafe requests.

Auto-diagnostic tools are read-only, local, bounded, redacted, and do not require per-command approval after the technician starts safe autodiagnosis. Do not request fixes, sudo, restarts, package operations, permission changes, database clients, external network calls, or shell commands through diagnostic tools.

Allowed diagnostic tools and arguments:
- get_uptime {}
- get_memory {}
- get_disk_usage {}
- list_listening_tcp_ports {}
- list_processes {}
- get_service_status {service}
- get_service_active_state {service}
- get_service_enabled_state {service}
- get_service_unit {service}
- get_service_properties {service, properties:[names]}
- get_recent_journal {service, lines}
- curl_local {port, path} or {url}; localhost/127.0.0.1 HTTP only
- list_directory {path}
- stat_path {path}
- read_text_file {path, max_lines}
- tail_file {path, lines}
- head_file {path, lines}
- grep_file {path, pattern, max_matches}
- grep_directory {path, pattern, max_matches}; only narrow app/config directories

Use observations to infer service names, ports, and paths, but keep requests narrow. Config and .env files may be read because the backend redacts sensitive values. Never request private keys, .ssh paths, /etc/shadow, /proc/*/environ, /run/secrets, database data directories, or broad recursive searches.

Return JSON only.

For a diagnostic tool call:
{"mode":"diagnostic_tool","tool":"get_service_status","arguments":{"service":"nginx.service"},"intent":"...","expected_signal":"...","evidence_basis":"...","evidence_gap":"..."}

When a fix or mutation is needed, stop auto-diagnosis with a command proposal for human review:
{"mode":"command_proposal","command":"sudo -n systemctl restart nginx","intent":"...","expected_signal":"...","risk_level":"medium","rollback_note":"...","evidence_basis":"...","evidence_gap":"..."}
"""


class Planner:
    def __init__(self, provider: LlmProvider | None = None):
        self.provider = provider or get_llm_provider()

    def propose_next_command(
        self,
        ticket: dict,
        customer_system: dict,
        observations: list[dict],
        safety_policy: str,
        related_ticket: dict | None = None,
        run_id: str | None = None,
    ) -> CommandProposal:
        messages = [
            {
                "role": "system",
                "content": PLANNER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": str(
                    redact_payload(
                        {
                            "ticket": ticket,
                            "customer_system": customer_system,
                            "related_ticket": related_ticket,
                            "recent_observations": observations[-8:],
                            "anti_loop_context": _anti_loop_context(observations),
                            "safety_policy": safety_policy,
                        },
                        get_settings().configured_secrets(),
                    )
                ),
            },
        ]
        try:
            payload = complete_json_with_metrics(self.provider, messages, timeout=30.0, operation="planner.propose_next_command", run_id=run_id)
            return CommandProposal.model_validate(payload)
        except ValidationError as exc:
            raise AgentError(f"Planner returned invalid command proposal: {exc}") from exc

    def propose_diagnostic_tool(
        self,
        ticket: dict,
        customer_system: dict,
        observations: list[dict],
        related_ticket: dict | None = None,
        run_id: str | None = None,
    ) -> DiagnosticToolProposal:
        messages = [
            {"role": "system", "content": DIAGNOSTIC_TOOL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": str(
                    redact_payload(
                        {
                            "ticket": ticket,
                            "customer_system": customer_system,
                            "related_ticket": related_ticket,
                            "recent_observations": observations[-12:],
                            "anti_loop_context": _anti_loop_context(observations),
                            "remaining_auto_diagnostic_budget": max(0, 12 - len([item for item in observations if item.get("source") == "auto_diagnostic"])),
                        },
                        get_settings().configured_secrets(),
                    )
                ),
            },
        ]
        try:
            payload = complete_json_with_metrics(self.provider, messages, timeout=30.0, operation="planner.propose_diagnostic_tool", run_id=run_id)
            proposal = DiagnosticToolProposal.model_validate(payload)
            if proposal.mode == "diagnostic_tool" and not proposal.tool:
                raise AgentError("Diagnostic planner omitted tool name")
            if proposal.mode == "command_proposal" and not proposal.command:
                raise AgentError("Diagnostic planner omitted command proposal")
            return proposal
        except ValidationError as exc:
            raise AgentError(f"Planner returned invalid diagnostic proposal: {exc}") from exc


SAFETY_POLICY_SUMMARY = (
    "Every command requires technician approval. sudo and compound/unrecognized commands require typed confirmation. "
    "Blocked: broad rm -rf, database deletion/reinitialization, chmod -R 777 on critical paths, deleting logs/history, "
    "disabling firewall/security/audit controls, reading likely secrets, or superuser workarounds. Prefer diagnosis "
    "before fixes, targeted persistent fixes over temporary workarounds, and validation evidence before activity submission."
)


def _anti_loop_context(observations: list[dict]) -> dict[str, Any]:
    commands: list[str] = []
    negative_findings: list[str] = []
    rejected_commands: list[str] = []
    guidance: list[str] = []
    for observation in observations:
        command = str(observation.get("command") or observation.get("blocked_command") or "").strip()
        status = str(observation.get("status") or "").lower()
        if command:
            commands.append(command)
        if status == "rejected" and command:
            rejected_commands.append(command)
        if observation.get("guidance"):
            guidance.append(str(observation["guidance"]))
        output = str(observation.get("output") or "")
        exit_code = observation.get("exit_code")
        if command and exit_code == 0 and not output.strip():
            negative_findings.append(f"{command} returned no output")

    repeated_commands = sorted({command for command in commands if commands.count(command) > 1})
    return {
        "recent_commands": commands[-8:],
        "repeated_commands": repeated_commands,
        "rejected_commands": rejected_commands[-4:],
        "technician_guidance": guidance[-4:],
        "negative_findings": negative_findings[-4:],
        "instruction": "Do not repeat recent, rejected, or equivalent commands unless technician guidance explicitly asks for a retry; use negative findings as evidence and pivot to a new hypothesis or concrete resource.",
    }
