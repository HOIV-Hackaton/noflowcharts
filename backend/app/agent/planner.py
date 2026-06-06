from pydantic import BaseModel, Field, ValidationError, field_validator

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

    @field_validator("command_class_hint", mode="before")
    @classmethod
    def ignore_invalid_command_class_hint(cls, value):
        if value is None or value in {item.value for item in CommandClassification}:
            return value
        return None


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
                "content": (
                    "You are an AI service desk troubleshooting planner. Propose exactly one Ubuntu shell command "
                    "for a human technician to review. Prefer diagnosis before fixes, minimal targeted changes, "
                    "and validation that proves customer benefit is restored. Never propose commands that read secrets, "
                    "delete data, clear logs/history, disable security controls, or apply blanket permissions. "
                    "Do not repeat a command when recent observations already contain its answer; use those observations "
                    "to choose the next smallest diagnostic or fix. Prefer read-only commands without sudo when they provide "
                    "enough evidence. Use sudo -n only for targeted privileged commands that truly need it, so commands fail "
                    "fast instead of prompting. For Linux service incidents, first check the expected listener, then inspect "
                    "the relevant systemd unit with systemctl cat, enabled/active state, and recent journal logs. If an "
                    "EnvironmentFile is involved, inspect only relevant non-secret keys like PORT or HOST rather than dumping "
                    "the full file. If a service is disabled, enable it separately from starting it. If a config value is wrong, "
                    "make the smallest targeted edit and then restart only the affected service. "
                    "For final validation after a fix, prefer read-only checks and, when safe and proportionate, "
                    "evidence that the fix persists after a relevant service restart or equivalent configuration check. "
                    "Use bounded HTTP validation such as curl --max-time 5 -fsS. Run provided public validation scripts only "
                    "after direct evidence indicates the fix is likely correct. "
                    "Return JSON only with keys: intent, command, expected_signal, risk_level, command_class_hint, rollback_note."
                ),
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
    "disabling firewall/security/audit controls, reading likely secrets, or superuser workarounds."
)
