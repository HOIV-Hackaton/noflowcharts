import pytest

from app.agent import providers
from app.agent.providers import AzureOpenAiProvider
from app.core.config import Settings
from app.core.errors import AgentError, ConfigurationError
from app.services.activity_generator import ActivityGenerator, GeneratedActivityDraft


def test_missing_azure_config_fails_only_when_provider_is_used():
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="",
        azure_openai_api_key="",
        azure_openai_deployment="",
        azure_openai_api_version="",
    )

    with pytest.raises(ConfigurationError):
        AzureOpenAiProvider(settings=settings)


def test_foundry_project_endpoint_uses_openai_compatible_client_without_api_version(monkeypatch):
    created = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
            self.chat = type("Chat", (), {"completions": object()})()

    monkeypatch.setattr(providers, "OpenAI", FakeOpenAI)
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.services.ai.azure.com/api/projects/demo",
        azure_openai_api_key="azure-secret",
        azure_openai_deployment="gpt-test",
    )

    provider = AzureOpenAiProvider(settings=settings)

    assert provider.deployment == "gpt-test"
    assert created["base_url"] == "https://example.services.ai.azure.com/api/projects/demo/openai/v1/"
    assert created["api_key"] == "azure-secret"


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


def test_generated_activity_draft_coerces_list_text_fields():
    draft = GeneratedActivityDraft.model_validate(
        {
            "summary": "Restored service.",
            "root_cause": "Service was stopped.",
            "actions_taken": ["Checked status.", "Restarted service.", "Validated endpoint."],
            "commands_summary": "Used service and HTTP validation commands.",
            "validation_result": "Endpoint returned ok.",
            "description": "Restored service after restart.",
        }
    )

    assert draft.actions_taken == "Checked status.\nRestarted service.\nValidated endpoint."


def test_activity_generator_prompt_requires_detailed_grounded_technician_log():
    class FakeProvider:
        def __init__(self):
            self.messages = None

        def complete_json(self, messages, timeout=45.0):
            self.messages = messages
            return {
                "summary": "Restored the customer-facing status API.",
                "root_cause": "nginx was inactive, which prevented the API proxy from serving requests.",
                "actions_taken": "Checked service state, reviewed recent service logs, restarted nginx, and validated the endpoint.",
                "commands_summary": "Used service status, journal review, service restart, and HTTP validation commands without secret output.",
                "validation_result": "The service reported active and the health endpoint returned successfully.",
                "description": "Restored the status API after confirming nginx was inactive and validating service recovery.",
            }

    provider = FakeProvider()
    draft = ActivityGenerator(provider=provider).generate({}, {}, [], [], {})
    prompt = provider.messages[0]["content"]

    assert draft.summary == "Restored the customer-facing status API."
    assert "detailed technician log" in prompt
    assert "Do not assume facts" in prompt
    assert "technical root cause" in prompt
    assert "concrete proof" in prompt
    assert "do not include secrets" in prompt
