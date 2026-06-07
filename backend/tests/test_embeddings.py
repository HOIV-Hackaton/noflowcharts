from app.repositories.knowledge import VECTOR_DIMENSIONS
from app.services import embeddings
from app.services.embeddings import AzureOpenAiEmbeddingProvider


class FakeSettings:
    azure_openai_endpoint = "https://example.services.ai.azure.com"
    azure_openai_api_key = "test-key"
    azure_openai_embedding_deployment = "text-embedding-3-large"
    azure_openai_api_version = "2024-10-21"

    def require_azure_openai_embeddings(self):
        return None

    def uses_foundry_project_endpoint(self):
        return False

    def configured_secrets(self):
        return [self.azure_openai_api_key]


class FakeEmbeddingResponse:
    class Item:
        embedding = [0.0] * VECTOR_DIMENSIONS

    data = [Item()]


def test_embedding_provider_requests_repository_vector_dimensions(monkeypatch):
    calls = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            calls.append(kwargs)
            return FakeEmbeddingResponse()

    class FakeAzureOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(embeddings, "AzureOpenAI", FakeAzureOpenAI)

    provider = AzureOpenAiEmbeddingProvider(settings=FakeSettings())
    vector = provider.embed("hello")

    assert len(vector) == VECTOR_DIMENSIONS
    assert calls[0]["model"] == "text-embedding-3-large"
    assert calls[0]["dimensions"] == VECTOR_DIMENSIONS
