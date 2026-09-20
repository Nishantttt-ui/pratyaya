"""Google Gemini adapter (Google AI Studio free tier)."""

from __future__ import annotations

import asyncio
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
    LLMUnavailableError,
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

    def __init__(
        self, api_key: str, model: str, timeout: float = 20.0, thinking_budget: int = 0
    ) -> None:
        if not api_key:
            raise LLMAuthError("GEMINI_API_KEY is not set")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        # Gemini 3 models spend tokens reasoning internally before emitting any
        # text, and that budget is drawn from maxOutputTokens. This task is not
        # a reasoning task: the decision, the reason codes and the citations are
        # all settled before the model is called, and its job is to restate them
        # readably. Thinking would spend tokens and latency on nothing, and at a
        # small maxOutputTokens it consumes the entire budget and returns empty
        # text with finishReason MAX_TOKENS. Disabled by default; set a positive
        # budget if a future prompt genuinely needs deliberation.
        self._thinking_budget = thinking_budget

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResult:
        """Generate, retrying briefly on a transient provider failure.

        Free inference tiers return 503 under load with some regularity. Two
        short retries turn most of those into a successful call; anything that
        survives them reaches the caller as an error and the deterministic
        notice is served.
        """
        last: LLMError | None = None
        for attempt in range(3):
            try:
                return await self._generate_once(
                    system=system, user=user, max_tokens=max_tokens, temperature=temperature
                )
            except (LLMUnavailableError, LLMRateLimitError) as exc:
                last = exc
                if attempt < 2:
                    await asyncio.sleep(0.8 * (2**attempt))
        raise last  # type: ignore[misc]

    async def _generate_once(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingBudget": self._thinking_budget},
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
        if response.status_code in (500, 502, 503, 504):
            raise LLMUnavailableError(
                f"Gemini temporarily unavailable (HTTP {response.status_code})"
            )
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
        finish = candidates[0].get("finishReason")

        if not text:
            # An empty completion is a provider failure, not an explanation.
            # Raising here rather than returning "" means the caller falls back
            # to the deterministic notice, so the applicant never receives a
            # blank reason for a credit decision.
            raise LLMError(
                f"Gemini returned no text (finishReason={finish}). "
                "The deterministic notice will be served instead."
            )
        usage = body.get("usageMetadata", {})
        # Record the version the API actually served, not the identifier we
        # asked for. Hosted model names are aliases that retire and re-point:
        # `gemini-2.0-flash` was withdrawn during this project's development and
        # returned a 404. For a regulated decision the audit trail has to say
        # which model produced the wording, so the resolved version wins over
        # the requested one whenever the response reports it.
        resolved = body.get("modelVersion") or self._model
        return LLMResult(
            text=text,
            provider=self.name,
            model=resolved,
            latency_ms=latency_ms,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            finish_reason=finish,
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
