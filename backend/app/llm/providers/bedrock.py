"""AWS Bedrock adapter - the reference target named in the problem brief.

Honest status
-------------
This adapter is written against the Bedrock Runtime ``Converse`` API and is
wired into the same factory as every other provider, but it has **not been
executed against a live endpoint**, because this project was built without AWS
access. It is included because it demonstrates the point of the abstraction:
moving this system onto Bedrock is a configuration change
(``LLM_PROVIDER=bedrock``) plus an IAM role, not a rewrite. Nothing above this
layer knows which provider answered.

``boto3`` is imported lazily so that the dependency is only required when this
provider is actually selected.

Credentials are never read from application configuration. They resolve through
the standard AWS chain - task role, instance profile, SSO, or environment - so
that a deployed service can use short-lived role credentials and no long-lived
secret ever lands in a config file.
"""

from __future__ import annotations

import time
from typing import ClassVar

from backend.app.llm.base import (
    LLMAuthError,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMTimeoutError,
)


class BedrockProvider(LLMProvider):
    name: ClassVar[str] = "bedrock"

    def __init__(self, model_id: str, region: str = "ap-south-1", timeout: float = 30.0) -> None:
        self._model_id = model_id
        self._region = region
        self._timeout = timeout
        self._client = None  # built lazily on first use

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3  # noqa: PLC0415 - deliberately lazy
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise LLMError(
                "LLM_PROVIDER=bedrock requires boto3. Install it with: "
                "uv pip install boto3"
            ) from exc

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self._region,
            config=Config(
                read_timeout=self._timeout,
                connect_timeout=5,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )
        return self._client

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResult:
        import asyncio

        client = self._get_client()
        started = time.perf_counter()

        def _call():
            return client.converse(
                modelId=self._model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )

        try:
            # boto3 is synchronous; run it off the event loop so it cannot
            # block every other request being served by this worker.
            body = await asyncio.to_thread(_call)
        except Exception as exc:  # noqa: BLE001 - botocore raises a wide surface
            name = type(exc).__name__
            if "Credential" in name or "AccessDenied" in name or "UnrecognizedClient" in name:
                raise LLMAuthError(f"Bedrock credentials rejected: {exc}") from exc
            if "Throttling" in name or "TooManyRequests" in name:
                raise LLMError(f"Bedrock throttled the request: {exc}") from exc
            if "ReadTimeout" in name or "ConnectTimeout" in name:
                raise LLMTimeoutError(f"Bedrock timed out after {self._timeout}s") from exc
            raise LLMError(f"Bedrock call failed: {exc}") from exc

        blocks = body.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block.get("text", "") for block in blocks).strip()
        usage = body.get("usage", {})
        return LLMResult(
            text=text,
            provider=self.name,
            model=self._model_id,
            latency_ms=self._elapsed_ms(started),
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
            finish_reason=body.get("stopReason"),
        )

    async def health_check(self) -> bool:
        try:
            self._get_client()
            return True
        except LLMError:
            return False
