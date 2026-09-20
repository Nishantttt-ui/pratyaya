"""Groq adapter, speaking the OpenAI-compatible chat-completions protocol."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from backend.app.llm.base import (
    LLMAuthError,
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMResult,
    LLMTimeoutError,
)


class GroqProvider(LLMProvider):
    """Groq's inference API.

    The wire format is OpenAI-compatible, so this adapter also works against
    any OpenAI-protocol endpoint by overriding ``base_url`` - useful if the
    evaluator wants to point the system at their own gateway.
    """

    name: ClassVar[str] = "groq"
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 20.0,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise LLMAuthError("GROQ_API_KEY is not set")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Groq timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Groq transport failure: {exc}") from exc

        if response.status_code in (401, 403):
            raise LLMAuthError("Groq rejected the API key")
        if response.status_code == 429:
            raise LLMRateLimitError("Groq rate limit reached")
        if response.status_code >= 400:
            raise LLMError(f"Groq returned HTTP {response.status_code}: {response.text[:300]}")

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise LLMError("Groq returned no choices")
        usage = body.get("usage", {})
        return LLMResult(
            text=(choices[0]["message"]["content"] or "").strip(),
            provider=self.name,
            model=self._model,
            latency_ms=self._elapsed_ms(started),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            finish_reason=choices[0].get("finish_reason"),
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False
