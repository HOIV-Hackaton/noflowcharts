from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = BACKEND_DIR / "data" / "app.db"


class Settings(BaseSettings):
    phoenix_api_base_url: str | None = None
    phoenix_api_token: str | None = None

    ssh_private_key_path: str | None = None
    ssh_username: str | None = None

    sqlite_database_url: str = Field(default=f"sqlite:///{DEFAULT_SQLITE_PATH}")

    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_api_version: str | None = None

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def require_phoenix(self) -> None:
        missing = []
        if not self.phoenix_api_base_url:
            missing.append("PHOENIX_API_BASE_URL")
        if not self.phoenix_api_token:
            missing.append("PHOENIX_API_TOKEN")
        if missing:
            raise RuntimeError(f"Missing required Phoenix setting(s): {', '.join(missing)}")

    def require_ssh_key(self) -> None:
        if not self.ssh_private_key_path:
            raise RuntimeError("Missing required SSH setting: SSH_PRIVATE_KEY_PATH")

    def require_azure_openai(self) -> None:
        missing = []
        if not self.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.azure_openai_api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not self.azure_openai_deployment:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        if not self.uses_foundry_project_endpoint() and not self.azure_openai_api_version:
            missing.append("AZURE_OPENAI_API_VERSION")
        if missing:
            raise RuntimeError(f"Missing required Azure OpenAI setting(s): {', '.join(missing)}")

    def require_azure_openai_embeddings(self) -> None:
        missing = []
        if not self.azure_openai_endpoint:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.azure_openai_api_key:
            missing.append("AZURE_OPENAI_API_KEY")
        if not self.azure_openai_embedding_deployment:
            missing.append("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        if not self.uses_foundry_project_endpoint() and not self.azure_openai_api_version:
            missing.append("AZURE_OPENAI_API_VERSION")
        if missing:
            raise RuntimeError(f"Missing required Azure OpenAI embedding setting(s): {', '.join(missing)}")

    def uses_foundry_project_endpoint(self) -> bool:
        endpoint = self.azure_openai_endpoint or ""
        return ".services.ai.azure.com" in endpoint and "/api/projects/" in endpoint

    def configured_secrets(self) -> list[str]:
        return [
            secret
            for secret in (
                self.phoenix_api_token,
                self.azure_openai_api_key,
            )
            if secret
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
