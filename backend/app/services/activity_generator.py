from typing import Any

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError, field_validator

from app.agent.providers import LlmProvider, complete_json_with_metrics, get_llm_provider
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

    @field_validator("summary", "root_cause", "actions_taken", "commands_summary", "validation_result", "description", mode="before")
    @classmethod
    def coerce_text_field(cls, value: Any) -> Any:
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item is not None)
        return value


ACTIVITY_SYSTEM_PROMPT = """You are the final analysis agent for an AI-assisted service desk backend. You draft Phoenix ERP activity documentation for a human technician after diagnosis, execution, and verification are complete.

Write a detailed technician log that helps the next technician understand what was found, what was changed, and how restoration was proven. Optimize for the grader: technical root cause, working persistent fix, no regression/data loss, and complete useful summary.

Rules:
- Do not assume facts that are not present in the ticket, actions, command results, or validation evidence.
- If evidence is incomplete, state the concrete limitation instead of inventing certainty.
- The root_cause must be the technical cause, not just the customer symptom.
- Actions must list diagnosis, fix, and validation steps in chronological order.
- Commands summary must summarize relevant command classes and targets without raw secret-bearing output.
- Validation must include concrete proof that customer benefit was restored, using successful command results and human-confirmed validation evidence.
- Preserve safety: do not include secrets, tokens, private keys, passwords, raw environment contents, or unnecessary raw log excerpts.
- Be specific about persistence when evidence exists, such as service restart checks, enabled-state checks, config syntax checks, or reboot-safe configuration changes.
- Keep the wording professional and technical. Prefer clear paragraphs or semicolon-separated steps over vague phrases.
- Every JSON value must be a string. Do not return arrays, objects, markdown lists, or null values. In particular, actions_taken must be one string, not a JSON array.

Return JSON only with keys: summary, root_cause, actions_taken, commands_summary, validation_result, description.

Field guidance:
- summary: one sentence describing the restored customer-facing service or capability.
- root_cause: one to three sentences naming the underlying technical cause and evidence.
- actions_taken: ordered technician log of diagnosis, fix, and validation.
- commands_summary: concise sanitized summary of command classes, not raw output.
- validation_result: concrete evidence that the customer benefit is restored and, when shown, persists.
- description: polished ERP note combining the essential root cause, actions, and result without secrets.
"""


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
        run_id: str | None = None,
    ) -> GeneratedActivityDraft:
        messages = [
            {
                "role": "system",
                "content": ACTIVITY_SYSTEM_PROMPT,
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
            payload = complete_json_with_metrics(self.provider, messages, timeout=45.0, operation="activity.generate_draft", run_id=run_id)
            return GeneratedActivityDraft.model_validate(payload)
        except PydanticValidationError as exc:
            raise AgentError(f"Activity generator returned invalid draft: {exc}") from exc
