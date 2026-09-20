"""Ollama adapter - a fully local model, used as the offline fallback.

This exists for demo resilience. Every hosted provider in this project runs on
a free tier, which means rate limits and network dependence. If the venue
network fails or a quota is exhausted mid-demonstration, switching
``LLM_PROVIDER=ollama`` keeps the explanation layer working with no internet
at all. The decisioning model is local regardless, so in that mode the entire
system runs offline.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from backend.app.llm.base import (
    LLMError,
    LLMProvider,
    LLMResult,
    LLMTimeoutError,
)


class OllamaProvider(LLMProvider):
    name: ClassVar[str] = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout: float = 60.0,
    ) -> None:
        # Local CPU inference is slower than a hosted GPU, so the default
        # timeout here is deliberately more generous than the hosted providers'.
        self._model = model
        self._base_url = base_url.rstrip("/")
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
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Ollama timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama unreachable at {self._base_url}: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(f"Ollama returned HTTP {response.status_code}: {response.text[:300]}")

        body = response.json()
        return LLMResult(
            text=(body.get("message", {}).get("content") or "").strip(),
            provider=self.name,
            model=self._model,
            latency_ms=self._elapsed_ms(started),
            input_tokens=body.get("prompt_eval_count"),
            output_tokens=body.get("eval_count"),
            finish_reason=body.get("done_reason"),
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
            return response.status_code == 200
        except httpx.HTTPError:
            return False
