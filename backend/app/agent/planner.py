from pydantic import BaseModel, Field, ValidationError

from app.agent.providers import LlmProvider, get_llm_provider
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
                    "For final validation after a fix, prefer read-only checks and, when safe and proportionate, "
                    "evidence that the fix persists after a relevant service restart or equivalent configuration check. "
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
                        }
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
