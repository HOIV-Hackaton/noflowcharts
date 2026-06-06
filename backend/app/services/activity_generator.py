from typing import Any

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.agent.providers import LlmProvider, get_llm_provider
from app.core.errors import AgentError
from app.core.redaction import redact_payload
from app.core.config import get_settings


class GeneratedActivityDraft(BaseModel):
    summary: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    actions_taken: str = Field(min_length=1)
    commands_summary: str = Field(min_length=1)
    validation_result: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ActivityGenerator:
    def __init__(self, provider: LlmProvider | None = None):
        self.provider = provider or get_llm_provider()

    def generate(
        self,
        ticket: dict[str, Any],
        customer_system: dict[str, Any],
        actions: list[dict[str, Any]],
        command_results: list[dict[str, Any]],
        validation: dict[str, Any],
    ) -> GeneratedActivityDraft:
        messages = [
            {
                "role": "system",
                "content": (
                    "You draft Phoenix ERP activity documentation for a technician. Return JSON only with keys: "
                    "summary, root_cause, actions_taken, commands_summary, validation_result, description. "
                    "The root_cause must be the technical cause, not just the customer symptom. "
                    "Actions must list diagnosis and fix steps in order. Commands summary must describe command classes "
                    "without secrets or raw secret-bearing output. Validation must state concrete proof that customer benefit "
                    "is restored. Keep text concise and technically useful."
                ),
            },
            {
                "role": "user",
                "content": str(
                    redact_payload(
                        {
                            "ticket": ticket,
                            "customer_system": customer_system,
                            "actions": actions,
                            "command_results": command_results,
                            "validation": validation,
                        },
                        get_settings().configured_secrets(),
                    )
                ),
            },
        ]
        try:
            payload = self.provider.complete_json(messages, timeout=45.0)
            return GeneratedActivityDraft.model_validate(payload)
        except PydanticValidationError as exc:
            raise AgentError(f"Activity generator returned invalid draft: {exc}") from exc
