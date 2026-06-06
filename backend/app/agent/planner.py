from pydantic import BaseModel, Field, ValidationError

from app.agent.providers import LlmProvider, get_llm_provider
from app.core.errors import AgentError
from app.core.redaction import redact_payload
from app.core.config import get_settings
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


PLANNER_SYSTEM_PROMPT = """You are the backend troubleshooting planner for an AI-assisted service desk.

Your job is to propose exactly one Ubuntu shell command for a human technician to review. The backend will enforce approval and safety checks; you must still avoid unsafe or low-value commands.

Primary objective: solve hidden Linux service incidents accurately and safely. Optimize for correct root cause, a working customer-facing fix, persistence after restart/reboot when relevant, no regression/data loss, and useful activity documentation.

Operating rules:
- Do not assume context. Use only the ticket, customer system, observations, and safety policy supplied in the user message.
- Diagnose before fixing. When uncertain, choose a read-only diagnostic command that tests the most likely hypothesis or narrows the search space.
- Be very conservative with mutation. Propose a fix only after observations support a concrete technical cause.
- Propose the smallest targeted command that advances the investigation or fix. Avoid compound shell, pipes, sudo, package installs, broad file edits, broad restarts, and blanket permission changes unless clearly necessary.
- For the first command, or whenever recent observations do not identify a concrete service/config/path, the command must be read-only, must not use sudo, and must not use shell control operators.
- The command string must be a single simple command. Do not use &&, ||, ;, pipes, command substitution, newlines, or fallback chains.
- Never propose commands that read secrets, dump environment files, delete customer data, clear logs/history, disable firewall/audit/security controls, reinitialize databases, or work around permissions by running services as root.
- Prefer service-local and app-local checks: service status, recent logs, listening ports, config syntax, disk space, permissions on the exact affected path, and health endpoints inferred from evidence.
- After a fix, propose validation that proves customer benefit is restored. When safe and proportionate, validate persistence with a relevant service restart, config check, or enabled-state check before activity creation.
- If the previous command failed or was blocked, explain that in intent and propose the safest next diagnostic or safer alternative. Do not repeat the same failed command unless retrying is clearly justified.

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


class Planner:
    def __init__(self, provider: LlmProvider | None = None):
        self.provider = provider or get_llm_provider()

    def propose_next_command(
        self,
        ticket: dict,
        customer_system: dict,
        observations: list[dict],
        safety_policy: str,
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
                            "recent_observations": observations[-8:],
                            "safety_policy": safety_policy,
                        },
                        get_settings().configured_secrets(),
                    )
                ),
            },
        ]
        try:
            payload = self.provider.complete_json(messages)
            return CommandProposal.model_validate(payload)
        except ValidationError as exc:
            raise AgentError(f"Planner returned invalid command proposal: {exc}") from exc


SAFETY_POLICY_SUMMARY = (
    "Every command requires technician approval. sudo and compound/unrecognized commands require typed confirmation. "
    "Blocked: broad rm -rf, database deletion/reinitialization, chmod -R 777 on critical paths, deleting logs/history, "
    "disabling firewall/security/audit controls, reading likely secrets, or superuser workarounds. Prefer diagnosis "
    "before fixes, targeted persistent fixes over temporary workarounds, and validation evidence before activity submission."
)
