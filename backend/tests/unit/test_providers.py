"""LLM provider adapters.

These run against mocked transports rather than live endpoints. What is being
tested is the code this project owns: request shape, response parsing, and the
mapping from provider-specific HTTP failures onto the common exception
hierarchy the DecisionService relies on to decide when to fall back.
"""

from __future__ import annotations

import httpx
import pytest

from backend.app.llm.base import LLMAuthError, LLMError, LLMRateLimitError
from backend.app.llm.providers.gemini import GeminiProvider
from backend.app.llm.providers.groq import GroqProvider
from backend.app.llm.providers.ollama import OllamaProvider


def _patch(monkeypatch, response: httpx.Response):
    async def _post(self, *args, **kwargs):  # noqa: ANN001
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)


GEMINI_OK = {
    "candidates": [
        {"content": {"parts": [{"text": "Your application was not approved."}]},
         "finishReason": "STOP"}
    ],
    "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 45},
}

GROQ_OK = {
    "choices": [
        {"message": {"content": "Your application was not approved."}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 120, "completion_tokens": 45},
}


@pytest.mark.asyncio
async def test_gemini_parses_a_successful_response(monkeypatch):
    _patch(monkeypatch, httpx.Response(200, json=GEMINI_OK))
    result = await GeminiProvider("key", "gemini-2.0-flash").generate(system="s", user="u")
    assert result.text == "Your application was not approved."
    assert result.provider == "gemini"
    assert result.input_tokens == 120
    assert result.output_tokens == 45
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_gemini_maps_rejected_key_to_auth_error(monkeypatch):
    _patch(monkeypatch, httpx.Response(403, json={"error": "forbidden"}))
    with pytest.raises(LLMAuthError):
        await GeminiProvider("bad", "gemini-2.0-flash").generate(system="s", user="u")


@pytest.mark.asyncio
async def test_gemini_maps_throttling_to_rate_limit_error(monkeypatch):
    _patch(monkeypatch, httpx.Response(429, json={"error": "quota"}))
    with pytest.raises(LLMRateLimitError):
        await GeminiProvider("key", "gemini-2.0-flash").generate(system="s", user="u")


@pytest.mark.asyncio
async def test_gemini_reports_a_safety_block_rather_than_returning_empty(monkeypatch):
    """A blocked prompt must raise, so the caller falls back deterministically."""
    _patch(monkeypatch, httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(LLMError, match="SAFETY"):
        await GeminiProvider("key", "gemini-2.0-flash").generate(system="s", user="u")


def test_gemini_requires_a_key():
    with pytest.raises(LLMAuthError):
        GeminiProvider("", "gemini-2.0-flash")


@pytest.mark.asyncio
async def test_groq_parses_a_successful_response(monkeypatch):
    _patch(monkeypatch, httpx.Response(200, json=GROQ_OK))
    result = await GroqProvider("key", "llama-3.3-70b").generate(system="s", user="u")
    assert result.text == "Your application was not approved."
    assert result.provider == "groq"
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_groq_maps_auth_failure(monkeypatch):
    _patch(monkeypatch, httpx.Response(401, json={"error": "unauthorized"}))
    with pytest.raises(LLMAuthError):
        await GroqProvider("bad", "llama-3.3-70b").generate(system="s", user="u")


@pytest.mark.asyncio
async def test_ollama_parses_a_successful_response(monkeypatch):
    _patch(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "message": {"content": "Your application was not approved."},
                "prompt_eval_count": 100,
                "eval_count": 40,
                "done_reason": "stop",
            },
        ),
    )
    result = await OllamaProvider("llama3.2").generate(system="s", user="u")
    assert result.provider == "ollama"
    assert result.output_tokens == 40


@pytest.mark.asyncio
async def test_ollama_unreachable_raises_llm_error(monkeypatch):
    async def _post(self, *args, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    with pytest.raises(LLMError, match="unreachable"):
        await OllamaProvider("llama3.2").generate(system="s", user="u")


def test_factory_rejects_an_unknown_provider():
    from backend.app.core.config import get_settings
    from backend.app.llm.factory import build_provider

    settings = get_settings().model_copy(update={"llm_provider": "nope"})
    with pytest.raises(ValueError, match="Unsupported"):
        build_provider(settings)


def test_factory_requires_a_key_for_hosted_providers():
    from backend.app.core.config import get_settings
    from backend.app.llm.factory import build_provider

    settings = get_settings().model_copy(
        update={"llm_provider": "groq", "groq_api_key": None}
    )
    with pytest.raises(LLMAuthError, match="GROQ_API_KEY"):
        build_provider(settings)
