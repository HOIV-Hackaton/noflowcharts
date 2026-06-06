import json
from abc import ABC, abstractmethod
from typing import Any

from openai import AzureOpenAI, OpenAI

from app.core.config import Settings, get_settings
from app.core.errors import AgentError, ConfigurationError
from app.core.redaction import redact_text


class LlmProvider(ABC):
    @abstractmethod
    def complete_json(self, messages: list[dict[str, str]], timeout: float = 30.0) -> dict[str, Any]:
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

    def complete_json(self, messages: list[dict[str, str]], timeout: float = 30.0) -> dict[str, Any]:
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
            raise
        except Exception as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            raise AgentError(f"Azure OpenAI request failed: {message}") from exc
        if not isinstance(parsed, dict):
            raise AgentError("Azure OpenAI returned non-object JSON")
        return parsed


def get_llm_provider() -> LlmProvider:
    return AzureOpenAiProvider()
