"""Provider-agnostic contract for the language-model layer.

Design note
-----------
The LLM in this system sits strictly on the *explanation* path. A credit
decision is produced by a deterministic gradient-boosted model and is already
final before any provider here is called. These providers turn that decision,
plus retrieved regulatory text, into readable language. A provider outage,
a hallucination, or a swapped vendor can therefore change how a decision is
*described* - never what the decision *is*.

Two consequences follow, and both are enforced below:

* ``temperature`` defaults to ``0.0``. A regulated lender must be able to
  reproduce the explanation attached to any past decision during an audit.
* Every concrete provider is interchangeable behind ``generate()``, so the
  deployment target (Gemini, Groq, a local Ollama model, or AWS Bedrock) is a
  configuration choice rather than a code change.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass
from typing import ClassVar


class LLMError(RuntimeError):
    """Base class for every failure raised by a provider."""


class LLMAuthError(LLMError):
    """Credentials are missing, malformed, or rejected by the provider."""


class LLMRateLimitError(LLMError):
    """The provider throttled the request; the caller may retry later."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured budget."""


@dataclass(frozen=True)
class LLMResult:
    """A single completion, plus the metadata an audit trail needs."""

    text: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


class LLMProvider(abc.ABC):
    """Uniform interface every concrete provider implements."""

    name: ClassVar[str]

    @abc.abstractmethod
    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.0,
    ) -> LLMResult:
        """Return a completion for ``user``, steered by the ``system`` prompt.

        Raises:
            LLMAuthError: credentials missing or rejected.
            LLMRateLimitError: provider throttled the request.
            LLMTimeoutError: no response within the timeout budget.
            LLMError: any other provider-side failure.
        """

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Cheap liveness probe, surfaced on the service ``/health`` endpoint."""

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
