"""Google Gemini adapter (Google AI Studio free tier)."""

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


class GeminiProvider(LLMProvider):
    """Calls the Gemini ``generateContent`` endpoint.

    The API key is sent in the ``x-goog-api-key`` header rather than as a query
    parameter. Query strings are routinely captured by proxies, load balancers
    and access logs, so keeping the credential in a header avoids writing it to
    disk somewhere outside our control.
    """

    name: ClassVar[str] = "gemini"
    BASE_URL: ClassVar[str] = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, timeout: float = 20.0) -> None:
        if not api_key:
            raise LLMAuthError("GEMINI_API_KEY is not set")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        url = f"{self.BASE_URL}/models/{self._model}:generateContent"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "x-goog-api-key": self._api_key,
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Gemini timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini transport failure: {exc}") from exc

        self._raise_for_status(response)
        return self._parse(response.json(), self._elapsed_ms(started))

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise LLMAuthError("Gemini rejected the API key")
        if response.status_code == 429:
            raise LLMRateLimitError("Gemini rate limit reached")
        if response.status_code >= 400:
            raise LLMError(f"Gemini returned HTTP {response.status_code}: {response.text[:300]}")

    def _parse(self, body: dict[str, Any], latency_ms: int) -> LLMResult:
        candidates = body.get("candidates") or []
        if not candidates:
            # Most often the safety filter blocked the prompt outright.
            reason = body.get("promptFeedback", {}).get("blockReason", "unknown")
            raise LLMError(f"Gemini returned no candidates (blockReason={reason})")

        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()
        usage = body.get("usageMetadata", {})
        return LLMResult(
            text=text,
            provider=self.name,
            model=self._model,
            latency_ms=latency_ms,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            finish_reason=candidates[0].get("finishReason"),
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/models/{self._model}",
                    headers={"x-goog-api-key": self._api_key},
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False
