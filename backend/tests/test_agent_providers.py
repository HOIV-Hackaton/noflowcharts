import pytest

from app.agent import providers
from app.agent.providers import AzureOpenAiProvider
from app.core.config import Settings
from app.core.errors import AgentError, ConfigurationError
from app.services.activity_generator import ActivityGenerator


def test_missing_azure_config_fails_only_when_provider_is_used():
    settings = Settings(_env_file=None)

    with pytest.raises(ConfigurationError):
        AzureOpenAiProvider(settings=settings)


def test_azure_provider_redacts_secrets_on_failure(monkeypatch):
    class FailingCompletions:
        def create(self, **kwargs):
            raise RuntimeError("bad azure-secret")

    class FakeAzureOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FailingCompletions()})()

    monkeypatch.setattr(providers, "AzureOpenAI", FakeAzureOpenAI)
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="azure-secret",
        azure_openai_deployment="gpt",
        azure_openai_api_version="2024-02-01",
    )

    with pytest.raises(AgentError) as exc_info:
        AzureOpenAiProvider(settings=settings).complete_json([])

    assert "azure-secret" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_azure_provider_rejects_invalid_and_non_object_json(monkeypatch):
    class FakeCompletions:
        def __init__(self, content):
            self.content = content

        def create(self, **kwargs):
            message = type("Message", (), {"content": self.content})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    class FakeAzureOpenAI:
        content = "[]"

        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions(self.content)})()

    monkeypatch.setattr(providers, "AzureOpenAI", FakeAzureOpenAI)
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="azure-secret",
        azure_openai_deployment="gpt",
        azure_openai_api_version="2024-02-01",
    )

    with pytest.raises(AgentError):
        AzureOpenAiProvider(settings=settings).complete_json([])

    FakeAzureOpenAI.content = "not-json"
    with pytest.raises(AgentError):
        AzureOpenAiProvider(settings=settings).complete_json([])


def test_activity_generator_converts_invalid_draft_payload_to_agent_error():
    class FakeProvider:
        def complete_json(self, messages, timeout=45.0):
            return {"summary": "missing required fields"}

    with pytest.raises(AgentError):
        ActivityGenerator(provider=FakeProvider()).generate({}, {}, [], [], {})
