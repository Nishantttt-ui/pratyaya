"""Orchestrates a full credit assessment.

The ordering here encodes the project's central claim, so it is worth stating
plainly: **the decision is computed, the reasons are computed, the notice is
rendered, and only then is a language model consulted.** By the time any
provider is called, a complete and compliant answer already exists. The model's
output is an optional replacement for the narrative section, admitted only if
it passes an outbound guardrail.

The consequences are concrete. If the provider is down, over quota, slow, or
returns something that contradicts the decision, the applicant still receives a
correct notice with correct reasons and correct citations. Nothing about the
outcome, the reason codes or the recourse depends on the model.

Every assessment returns a ``provenance`` block recording which path was taken
and which guardrails fired, so a reviewer can tell at a glance whether a given
applicant's wording was generated or deterministic.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from backend.app.llm.base import LLMError, LLMProvider
from backend.app.llm.guardrails import check_prompt, verify_consistency
from backend.app.llm.prompts.explanation import SYSTEM_PROMPT, build_user_prompt
from backend.app.rag.store import VectorStore
from backend.app.services.notice import render_notice
from ml.explain.explainer import CreditExplainer, Explanation
from ml.explain.recourse import RecourseOption, find_recourse

logger = logging.getLogger(__name__)


@dataclass
class Provenance:
    """How this explanation was produced. Recorded on every assessment."""

    narrative_source: str  # "llm" or "deterministic_template"
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    guardrail_passed: bool = True
    guardrail_violations: list[str] = field(default_factory=list)
    fallback_reason: str | None = None


@dataclass
class AssessmentResult:
    decision: str
    probability_of_default: float
    threshold: float
    is_new_to_credit: bool
    adverse_reasons: list[dict]
    favourable_reasons: list[dict]
    recourse: list[dict]
    citations: list[dict]
    narrative: str
    deterministic_notice: str
    provenance: Provenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "probability_of_default": round(self.probability_of_default, 6),
            "threshold": round(self.threshold, 6),
            "is_new_to_credit": self.is_new_to_credit,
            "adverse_reasons": self.adverse_reasons,
            "favourable_reasons": self.favourable_reasons,
            "recourse": self.recourse,
            "citations": self.citations,
            "narrative": self.narrative,
            "deterministic_notice": self.deterministic_notice,
            "provenance": asdict(self.provenance),
        }


def build_retrieval_query(explanation: Explanation) -> str:
    """Compose the retrieval query from the decision, not from raw applicant data."""
    parts: list[str] = []
    if explanation.decision == "DECLINE":
        parts.append("reasons for rejection of a loan application must be communicated")
    else:
        parts.append("terms and conditions communicated to the borrower on sanction")
    if explanation.is_new_to_credit:
        parts.append(
            "applicant has no credit bureau record, new to credit, "
            "assessed on alternative data"
        )
        parts.append("consent for sharing bank transaction data")
    parts.extend(reason.label.lower() for reason in explanation.adverse_reasons[:3])
    return "; ".join(parts)


class DecisionService:
    """Produces a complete, explained credit decision."""

    def __init__(
        self,
        *,
        explainer: CreditExplainer,
        store: VectorStore | None = None,
        provider: LLMProvider | None = None,
        population: pd.DataFrame | None = None,
        top_k_citations: int = 3,
    ) -> None:
        self._explainer = explainer
        self._store = store
        self._provider = provider
        self._population = population
        self._top_k = top_k_citations

    async def assess(self, applicant: pd.DataFrame, *, top_n: int = 4) -> AssessmentResult:
        """Score, explain, and narrate one applicant."""
        explanation = self._explainer.explain(applicant, top_n=top_n)

        recourse: list[RecourseOption] = []
        if explanation.decision == "DECLINE" and self._population is not None:
            recourse = find_recourse(
                applicant, explainer=self._explainer, population=self._population
            )

        citations: list[dict] = []
        if self._store is not None:
            retrieved = self._store.search(build_retrieval_query(explanation), top_k=self._top_k)
            citations = [r.to_citation() for r in retrieved]

        # The compliant answer exists at this point, before any model is called.
        notice = render_notice(explanation, recourse=recourse, citations=citations)

        narrative, provenance = await self._narrate(explanation, recourse, citations, notice)

        return AssessmentResult(
            decision=explanation.decision,
            probability_of_default=explanation.probability_of_default,
            threshold=explanation.threshold,
            is_new_to_credit=explanation.is_new_to_credit,
            adverse_reasons=[r.to_dict() for r in explanation.adverse_reasons],
            favourable_reasons=[r.to_dict() for r in explanation.favourable_reasons],
            recourse=[o.to_dict() for o in recourse],
            citations=citations,
            narrative=narrative,
            deterministic_notice=notice,
            provenance=provenance,
        )

    async def _narrate(
        self,
        explanation: Explanation,
        recourse: list[RecourseOption],
        citations: list[dict],
        fallback: str,
    ) -> tuple[str, Provenance]:
        """Attempt an LLM narrative, falling back to the deterministic notice."""
        if self._provider is None:
            return fallback, Provenance(
                narrative_source="deterministic_template",
                fallback_reason="no LLM provider configured",
            )

        user_prompt = build_user_prompt(explanation, recourse=recourse, citations=citations)

        inbound = check_prompt(user_prompt)
        if not inbound.passed:
            logger.warning("inbound guardrail blocked prompt: %s", inbound.details)
            return fallback, Provenance(
                narrative_source="deterministic_template",
                guardrail_passed=False,
                guardrail_violations=[str(v) for v in inbound.violations],
                fallback_reason="inbound guardrail rejected the prompt",
            )

        try:
            result = await self._provider.generate(
                system=SYSTEM_PROMPT, user=user_prompt, max_tokens=500, temperature=0.0
            )
        except LLMError as exc:
            logger.warning("provider failed, using deterministic notice: %s", exc)
            return fallback, Provenance(
                narrative_source="deterministic_template",
                provider=getattr(self._provider, "name", None),
                fallback_reason=f"provider error: {type(exc).__name__}",
            )

        outbound = verify_consistency(result.text, decision=explanation.decision)
        if not outbound.passed:
            logger.warning("outbound guardrail rejected generation: %s", outbound.details)
            return fallback, Provenance(
                narrative_source="deterministic_template",
                provider=result.provider,
                model=result.model,
                latency_ms=result.latency_ms,
                guardrail_passed=False,
                guardrail_violations=[str(v) for v in outbound.violations],
                fallback_reason="outbound guardrail rejected the generated text",
            )

        return result.text, Provenance(
            narrative_source="llm",
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            guardrail_passed=True,
        )
