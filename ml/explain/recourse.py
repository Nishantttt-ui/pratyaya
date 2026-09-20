"""Actionable recourse: what would actually change this decision.

A decline with reasons attached is transparency. A decline that also tells the
applicant *what to change, by how much, and roughly how long it takes* is
inclusion - it converts a permanent rejection into a plan. For a first-time
borrower who has never been given a reason before, this is the part of the
system that has real-world value.

Method
------
For each factor the applicant can realistically move, we search for the
smallest change that brings their probability of default to the approval
threshold, holding every other feature fixed, and re-scoring with the real
model. These are genuine counterfactuals produced by querying the model, not
narrative generated afterwards.

Two constraints keep the advice honest:

* **Only actionable factors.** Age, education and employment sector are never
  suggested. Advising someone to be older is not recourse.
* **Only attainable targets.** Candidate values are drawn from the observed
  population distribution, capped at a percentile ceiling. The system will not
  tell an applicant to reach a balance only the top 1% maintain. If no
  attainable change flips the decision, that is reported honestly rather than
  padded with an impossible suggestion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ml.explain.feature_dictionary import Actionability, describe

# Never suggest a target beyond this percentile of the observed population.
ATTAINABILITY_CEILING = 0.85
SEARCH_STEPS = 24


@dataclass
class RecourseOption:
    feature: str
    label: str
    current_value: float
    target_value: float
    direction: str
    effort: str
    hint: str | None
    projected_pd: float

    def to_dict(self) -> dict:
        return asdict(self)


def _candidate_targets(
    population: pd.Series, current: float, higher_is_riskier: bool
) -> np.ndarray:
    """Attainable values in the improving direction, nearest change first."""
    clean = pd.to_numeric(population, errors="coerce").dropna()
    if clean.empty:
        return np.array([])

    if higher_is_riskier:
        floor = float(clean.quantile(1 - ATTAINABILITY_CEILING))
        if current <= floor:
            return np.array([])
        targets = np.linspace(current, floor, SEARCH_STEPS)
    else:
        ceiling = float(clean.quantile(ATTAINABILITY_CEILING))
        if current >= ceiling:
            return np.array([])
        targets = np.linspace(current, ceiling, SEARCH_STEPS)
    return targets[1:]


def find_recourse(
    applicant: pd.DataFrame,
    *,
    explainer,
    population: pd.DataFrame,
    max_options: int = 3,
) -> list[RecourseOption]:
    """Return the smallest attainable changes that would flip a decline.

    Args:
        applicant: one-row DataFrame of raw features.
        explainer: a ``CreditExplainer``, used to re-score counterfactuals.
        population: reference population defining what is attainable.
        max_options: how many options to return.
    """
    if len(applicant) != 1:
        raise ValueError("find_recourse() takes exactly one applicant row")

    threshold = explainer.threshold
    baseline_pd = float(explainer.predict_proba(applicant)[0])
    if baseline_pd <= threshold:
        return []  # already approved; nothing to remedy

    options: list[RecourseOption] = []
    for feature in explainer.features:
        meaning = describe(feature)
        if meaning.actionability is Actionability.FIXED or meaning.is_derived:
            continue
        if feature not in population.columns:
            continue

        current = applicant.iloc[0].get(feature)
        if current is None or pd.isna(current) or not isinstance(current, (int, float, np.number)):
            continue
        current = float(current)

        targets = _candidate_targets(population[feature], current, meaning.higher_is_riskier)
        if targets.size == 0:
            continue

        # Score every candidate in one batch rather than one call per step.
        probe = pd.concat([applicant] * len(targets), ignore_index=True)
        probe[feature] = targets
        # The instalment ratio is derived, so keep it consistent when the
        # underlying amount or tenure moves.
        if feature == "loan_amount_requested":
            probe["emi_to_income"] = np.clip(
                (targets * 1.17 / probe["loan_tenure_months"])
                / np.maximum(probe["monthly_income_declared"], 1),
                0.01, 5.0,
            )
        elif feature == "loan_tenure_months":
            probe["emi_to_income"] = np.clip(
                (probe["loan_amount_requested"] * 1.17 / np.maximum(targets, 1))
                / np.maximum(probe["monthly_income_declared"], 1),
                0.01, 5.0,
            )

        probabilities = explainer.predict_proba(probe)
        flipped = np.flatnonzero(probabilities <= threshold)
        if flipped.size == 0:
            continue

        first = int(flipped[0])
        options.append(
            RecourseOption(
                feature=feature,
                label=meaning.label,
                current_value=round(current, 4),
                target_value=round(float(targets[first]), 4),
                direction="decrease" if targets[first] < current else "increase",
                effort=str(meaning.actionability),
                hint=meaning.recourse_hint,
                projected_pd=round(float(probabilities[first]), 6),
            )
        )

    # Prefer the changes that are quickest to act on, then the smallest moves.
    effort_rank = {
        str(Actionability.IMMEDIATE): 0,
        str(Actionability.SHORT_TERM): 1,
        str(Actionability.LONG_TERM): 2,
    }
    options.sort(
        key=lambda o: (
            effort_rank.get(o.effort, 3),
            abs(o.target_value - o.current_value) / (abs(o.current_value) + 1e-9),
        )
    )
    return options[:max_options]
