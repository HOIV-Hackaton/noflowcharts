import json
import time
from abc import ABC, abstractmethod
from typing import Any

from openai import AzureOpenAI, OpenAI
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.errors import AgentError, ConfigurationError
from app.core.redaction import redact_text
from app.db.models import LlmUsageMetric
from app.db.session import engine


class LlmProvider(ABC):
    @abstractmethod
    def complete_json(
        self,
        messages: list[dict[str, str]],
        timeout: float = 30.0,
        operation: str = "llm.complete_json",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class AzureOpenAiProvider(LlmProvider):
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        try:
            self.settings.require_azure_openai()
        except RuntimeError as exc:
            raise ConfigurationError(str(exc)) from exc

        assert self.settings.azure_openai_endpoint is not None
        assert self.settings.azure_openai_api_key is not None
        self.deployment = self.settings.azure_openai_deployment
        assert self.deployment is not None
        if self.settings.uses_foundry_project_endpoint():
            self.client = OpenAI(
                base_url=f"{self.settings.azure_openai_endpoint.rstrip('/')}/openai/v1/",
                api_key=self.settings.azure_openai_api_key,
            )
        else:
            assert self.settings.azure_openai_api_version is not None
            self.client = AzureOpenAI(
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_key=self.settings.azure_openai_api_key,
                api_version=self.settings.azure_openai_api_version,
            )

    def complete_json(
        self,
        messages: list[dict[str, str]],
        timeout: float = 30.0,
        operation: str = "llm.complete_json",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        completion = None
        try:
            completion = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                timeout=timeout,
            )
            content = completion.choices[0].message.content
            if not content:
                raise AgentError("Azure OpenAI returned an empty response")
            parsed = json.loads(content)
        except AgentError:
            _record_llm_usage(operation, run_id, "azure_openai", self.deployment, started, completion, "agent_error")
            raise
        except Exception as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            _record_llm_usage(operation, run_id, "azure_openai", self.deployment, started, completion, message)
            raise AgentError(f"Azure OpenAI request failed: {message}") from exc
        if not isinstance(parsed, dict):
            _record_llm_usage(operation, run_id, "azure_openai", self.deployment, started, completion, "non_object_json")
            raise AgentError("Azure OpenAI returned non-object JSON")
        _record_llm_usage(operation, run_id, "azure_openai", self.deployment, started, completion, None)
        return parsed


def get_llm_provider() -> LlmProvider:
    return AzureOpenAiProvider()


def complete_json_with_metrics(
    provider: LlmProvider,
    messages: list[dict[str, str]],
    timeout: float,
    operation: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    try:
        return provider.complete_json(messages, timeout=timeout, operation=operation, run_id=run_id)
    except TypeError:
        return provider.complete_json(messages, timeout=timeout)


def _record_llm_usage(
    operation: str,
    run_id: str | None,
    provider: str,
    model: str,
    started: float,
    completion: Any,
    error: str | None,
) -> None:
    usage = getattr(completion, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
    metric = LlmUsageMetric(
        run_id=run_id,
        operation=operation,
        provider=provider,
        model=model,
        latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        error=error,
    )
    try:
        with Session(engine) as session:
            session.add(metric)
            session.commit()
    except Exception:
        # Observability must never break the human-approved troubleshooting flow.
        return
