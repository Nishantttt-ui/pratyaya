"""Selects the configured LLM provider at runtime.

This is the seam that makes the brief's "or equivalent" wording real. The
application depends on the ``LLMProvider`` abstraction; only this module knows
which vendor is actually in use. Swapping Gemini for Bedrock is an environment
variable, and no calling code changes.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.llm.base import LLMAuthError, LLMProvider
from backend.app.llm.providers.bedrock import BedrockProvider
from backend.app.llm.providers.gemini import GeminiProvider
from backend.app.llm.providers.groq import GroqProvider
from backend.app.llm.providers.ollama import OllamaProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Construct the provider named by ``settings.llm_provider``."""
    provider = settings.llm_provider
    key = settings.active_llm_key()

    if provider == "gemini":
        if key is None:
            raise LLMAuthError("LLM_PROVIDER=gemini but GEMINI_API_KEY is unset")
        return GeminiProvider(
            api_key=key.get_secret_value(),
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "groq":
        if key is None:
            raise LLMAuthError("LLM_PROVIDER=groq but GROQ_API_KEY is unset")
        return GroqProvider(
            api_key=key.get_secret_value(),
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "ollama":
        return OllamaProvider(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            timeout=max(settings.llm_timeout_seconds, 60.0),
        )

    if provider == "bedrock":
        return BedrockProvider(
            model_id=settings.bedrock_model_id,
            region=settings.aws_region,
            timeout=settings.llm_timeout_seconds,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}")


@lru_cache
def get_provider() -> LLMProvider:
    """Cached provider instance, used as a FastAPI dependency."""
    return build_provider(get_settings())
