"""Application configuration.

Every secret is read from the environment and held as a ``SecretStr`` so that it
cannot leak into logs or tracebacks through an accidental ``repr()``. No secret
has a usable default: a missing value fails fast at startup rather than silently
falling back to something insecure.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "groq", "ollama", "bedrock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Model artifacts ---
    model_path: str = "ml/artifacts/model.joblib"
    policy_corpus_path: str = "data/policy"

    # --- Application ---
    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # --- Database ---
    database_url: SecretStr = Field(
        ..., description="SQLAlchemy URL for PostgreSQL with the pgvector extension"
    )

    # --- Security ---
    jwt_secret: SecretStr = Field(..., min_length=1)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    cors_origins: str = "http://localhost:5173"

    # --- AI layer ---
    llm_provider: LLMProviderName = "gemini"
    llm_model: str = "gemini-3.1-flash-lite"
    llm_timeout_seconds: float = 20.0
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"
    aws_region: str = "ap-south-1"
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"

    # --- Demo accounts ---
    # Seeded only so the prototype can be run and reviewed. If unset in local
    # mode a random password is generated at startup and printed once to the
    # console, so the service never ships with a known default credential.
    demo_underwriter_password: SecretStr | None = None
    demo_applicant_password: SecretStr | None = None

    # --- Retrieval ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    retrieval_top_k: int = 4

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, v: SecretStr) -> SecretStr:
        """Stop the example placeholder from ever reaching a running service."""
        if "CHANGE_ME" in v.get_secret_value():
            raise ValueError(
                "JWT_SECRET is still the placeholder from .env.example. "
                'Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def active_llm_key(self) -> SecretStr | None:
        """Return the API key belonging to the currently selected provider.

        Returns None for an unrecognised provider rather than raising, so that
        the factory can report the unsupported name with a clear message
        instead of surfacing a bare KeyError from here.
        """
        return {
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "ollama": None,  # local, unauthenticated
            "bedrock": None,  # resolved via the AWS credential chain
        }.get(self.llm_provider)


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so configuration is parsed and validated exactly once."""
    return Settings()  # type: ignore[call-arg]
