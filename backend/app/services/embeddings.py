from openai import AzureOpenAI, OpenAI

from app.core.config import Settings, get_settings
from app.core.errors import AgentError, ConfigurationError
from app.core.redaction import redact_text


class AzureOpenAiEmbeddingProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        try:
            self.settings.require_azure_openai_embeddings()
        except RuntimeError as exc:
            raise ConfigurationError(str(exc)) from exc

        assert self.settings.azure_openai_endpoint is not None
        assert self.settings.azure_openai_api_key is not None
        self.deployment = self.settings.azure_openai_embedding_deployment
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

    def embed(self, text: str, timeout: float = 20.0) -> list[float]:
        try:
            response = self.client.embeddings.create(
                model=self.deployment,
                input=text,
                timeout=timeout,
            )
            if not response.data:
                raise AgentError("Azure OpenAI returned no embedding data")
            return list(response.data[0].embedding)
        except AgentError:
            raise
        except Exception as exc:
            message = redact_text(str(exc), self.settings.configured_secrets())
            status_code = getattr(exc, "status_code", None)
            if status_code == 404 or "Error code: 404" in message:
                message = (
                    f"deployment '{self.deployment}' was not found by Azure OpenAI. "
                    "Set AZURE_OPENAI_EMBEDDING_DEPLOYMENT to the actual Azure embedding deployment name, "
                    "not necessarily the model name. Original error: "
                    f"{message}"
                )
            raise AgentError(f"Azure OpenAI embedding request failed: {message}") from exc


def get_embedding_provider() -> AzureOpenAiEmbeddingProvider:
    return AzureOpenAiEmbeddingProvider()
