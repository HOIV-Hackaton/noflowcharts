from dataclasses import dataclass
from typing import Literal

from app.agent.providers import LlmProvider, get_llm_provider
from app.core.config import get_settings
from app.core.errors import AgentError, ConfigurationError
from app.core.redaction import redact_payload
from app.schemas.runs import CommandClassification
from app.services.safety import SafetyResult, classify_command


TerminalSafetyDecision = Literal["allow", "confirm", "block"]


@dataclass(frozen=True)
class TerminalSafetyResult:
    decision: TerminalSafetyDecision
    classification: CommandClassification
    reason: str
    deterministic: SafetyResult
    semantic_used: bool = False


SEMANTIC_SAFETY_PROMPT = """You review one technician-submitted Ubuntu shell command before it reaches a customer VM.

Return JSON only: {"decision":"allow|confirm|block","reason":"short technician-readable reason"}.

Rules:
- Never override deterministic blocked commands; those are handled before you.
- allow only if the command is clearly safe, non-interactive, scoped, and unlikely to damage data or leak secrets.
- confirm for sudo, mutating, compound, ambiguous, service restart, package, file permission, or unrecognized commands that may be valid but need human confirmation.
- block commands that are destructive, broad, interactive, secret-reading, log-clearing, database-deleting, nested shells/interpreters, or bypass safety controls.
- Prefer confirm over allow when uncertain.
"""


class TerminalSafetyReviewer:
    def __init__(self, provider: LlmProvider | None = None):
        self.provider = provider

    def review(self, command: str, context: dict | None = None) -> TerminalSafetyResult:
        deterministic = classify_command(command)
        if deterministic.blocked:
            return TerminalSafetyResult("block", deterministic.classification, deterministic.reason, deterministic, semantic_used=False)
        if deterministic.classification == CommandClassification.READ_ONLY:
            return TerminalSafetyResult("allow", deterministic.classification, deterministic.reason, deterministic, semantic_used=False)

        try:
            provider = self.provider or get_llm_provider()
            payload = provider.complete_json(
                [
                    {"role": "system", "content": SEMANTIC_SAFETY_PROMPT},
                    {
                        "role": "user",
                        "content": str(
                            redact_payload(
                                {
                                    "command": command,
                                    "deterministic_classification": deterministic.classification.value,
                                    "deterministic_reason": deterministic.reason,
                                    "run_context": context or {},
                                },
                                get_settings().configured_secrets(),
                            )
                        ),
                    },
                ],
                timeout=12.0,
            )
            decision = payload.get("decision")
            if decision not in {"allow", "confirm", "block"}:
                raise AgentError("Semantic safety reviewer returned invalid decision")
            reason = str(payload.get("reason") or deterministic.reason)
            return TerminalSafetyResult(decision, deterministic.classification, reason, deterministic, semantic_used=True)
        except (AgentError, ConfigurationError) as exc:
            return TerminalSafetyResult("confirm", deterministic.classification, f"Semantic safety unavailable; technician confirmation required: {exc}", deterministic, semantic_used=False)
