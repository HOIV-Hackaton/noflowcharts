import json
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import httpx
from openai import AzureOpenAI

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
        assert self.settings.azure_openai_api_version is not None
        self.deployment = self.settings.azure_openai_deployment
        assert self.deployment is not None
        self.endpoint = self.settings.azure_openai_endpoint.rstrip("/")
        self.api_key = self.settings.azure_openai_api_key
        self.use_responses_api = _is_project_endpoint(self.endpoint)
        self.client = None
        if not self.use_responses_api:
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.settings.azure_openai_api_version,
            )

    def complete_json(self, messages: list[dict[str, str]], timeout: float = 30.0) -> dict[str, Any]:
        try:
            if self.use_responses_api:
                content = self._complete_project_endpoint(messages, timeout)
            else:
                assert self.client is not None
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

    def _complete_project_endpoint(self, messages: list[dict[str, str]], timeout: float) -> str:
        response = httpx.post(
            f"{self.endpoint}/openai/v1/responses",
            headers={"Content-Type": "application/json", "api-key": self.api_key},
            json={
                "model": self.deployment,
                "input": _responses_input(messages),
                "text": {"format": {"type": "json_object"}},
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = redact_text(response.text, self.settings.configured_secrets())
            raise AgentError(f"Azure OpenAI request failed with status {response.status_code}: {detail}") from exc
        payload = response.json()
        return _extract_response_text(payload)


def _is_project_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.netloc.endswith("services.ai.azure.com") and "/api/projects/" in parsed.path


def _responses_input(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(f"{message['role'].upper()}: {message['content']}" for message in messages)


def _extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    for output in payload.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    raise AgentError("Azure OpenAI returned no response text")


def get_llm_provider() -> LlmProvider:
    return AzureOpenAiProvider()
