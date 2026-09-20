"""Fairness audit for credit decisions, expressed in lending terms.

Framing
-------
Generic fairness tooling talks about "selection rates" and "positive labels".
Lending has its own vocabulary and its own regulatory tests, so this module
reports:

* **Approval rate** per group, and the **disparate impact ratio** - the lowest
  group's approval rate divided by the highest. The widely used threshold is
  0.80: a ratio below it is the conventional trigger for investigating adverse
  impact.
* **Qualified approval rate** - among applicants who would *actually have
  repaid*, the share who were approved. This is equal-opportunity framed the way
  a credit committee would ask it: "of the good borrowers we turned away, who
  were they?" A model can look fair on raw approval rates while still failing
  creditworthy applicants from one group, and only this metric exposes it.
* **Default rate among approved** per group, which checks that fairness was not
  bought by simply taking on worse risk from one group.

Why the protected attribute never reaches the model
---------------------------------------------------
These attributes are used *only* here, for measurement. They are excluded from
the feature set by construction in ``ml/data/generator.feature_columns``.

That also constrains which mitigations are acceptable. Fairlearn's
``ThresholdOptimizer`` achieves parity by applying a different decision
threshold to each group. Statistically it works well, but in lending it means
an applicant's gender changes the bar they must clear, which is direct
discrimination rather than a remedy for it. The mitigations offered here
(``CorrelationRemover`` and ``ExponentiatedGradient``) need the protected
attribute at *training* time only. At decision time no protected attribute is
read, so two applicants with identical financial records receive an identical
decision regardless of group.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DISPARATE_IMPACT_THRESHOLD = 0.80


@dataclass
class GroupResult:
    group: str
    n: int
    approval_rate: float
    qualified_approval_rate: float
    default_rate_among_approved: float


@dataclass
class FairnessReport:
    attribute: str
    groups: list[GroupResult]
    disparate_impact_ratio: float
    qualified_approval_gap: float

    @property
    def passes_80_percent_rule(self) -> bool:
        return self.disparate_impact_ratio >= DISPARATE_IMPACT_THRESHOLD

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "group": g.group,
                    "n": g.n,
                    "approval_rate": round(g.approval_rate, 4),
                    "qualified_approval_rate": round(g.qualified_approval_rate, 4),
                    "default_rate_among_approved": round(g.default_rate_among_approved, 4),
                }
                for g in self.groups
            ]
        )

    def summary(self) -> str:
        verdict = "PASS" if self.passes_80_percent_rule else "FAIL"
        return (
            f"[{self.attribute}] disparate impact ratio = "
            f"{self.disparate_impact_ratio:.3f} ({verdict} at "
            f"{DISPARATE_IMPACT_THRESHOLD:.2f}); qualified-approval gap = "
            f"{self.qualified_approval_gap:.3f}"
        )


def audit_attribute(
    *,
    protected: pd.Series,
    approved: np.ndarray,
    defaulted: np.ndarray,
    attribute_name: str,
) -> FairnessReport:
    """Audit decisions against one protected attribute.

    Args:
        protected: group label per applicant.
        approved: boolean array, True where the application was approved.
        defaulted: array of realised outcomes (1 = defaulted).
        attribute_name: name used for reporting.
    """
    approved = np.asarray(approved).astype(bool)
    defaulted = np.asarray(defaulted).astype(int)
    would_repay = defaulted == 0

    results: list[GroupResult] = []
    for group in sorted(pd.Series(protected).dropna().unique()):
        mask = (protected == group).to_numpy()
        n = int(mask.sum())
        if n == 0:
            continue
        group_approved = approved[mask]
        qualified = mask & would_repay
        qualified_rate = (
            float(approved[qualified].mean()) if qualified.sum() else float("nan")
        )
        approved_in_group = mask & approved
        default_among_approved = (
            float(defaulted[approved_in_group].mean()) if approved_in_group.sum() else float("nan")
        )

        results.append(
            GroupResult(
                group=str(group),
                n=n,
                approval_rate=float(group_approved.mean()),
                qualified_approval_rate=qualified_rate,
                default_rate_among_approved=default_among_approved,
            )
        )

    approval_rates = [r.approval_rate for r in results if r.n > 0]
    qualified_rates = [
        r.qualified_approval_rate for r in results
        if not np.isnan(r.qualified_approval_rate)
    ]

    di_ratio = (
        float(min(approval_rates) / max(approval_rates))
        if approval_rates and max(approval_rates) > 0
        else float("nan")
    )
    qualified_gap = (
        float(max(qualified_rates) - min(qualified_rates)) if qualified_rates else float("nan")
    )

    return FairnessReport(
        attribute=attribute_name,
        groups=results,
        disparate_impact_ratio=di_ratio,
        qualified_approval_gap=qualified_gap,
    )


def audit_all(
    frame: pd.DataFrame,
    *,
    approved: np.ndarray,
    defaulted: np.ndarray,
    attributes: list[str],
) -> dict[str, FairnessReport]:
    """Run the audit across every protected attribute."""
    return {
        attribute: audit_attribute(
            protected=frame[attribute],
            approved=approved,
            defaulted=defaulted,
            attribute_name=attribute,
        )
        for attribute in attributes
    }
