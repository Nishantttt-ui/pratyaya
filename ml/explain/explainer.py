"""Turns a model output into reason codes a person can read and act on.

What this produces, and why in this order
-----------------------------------------
For each applicant the explainer returns the decision, the calibrated
probability of default, and a ranked set of **reason codes**: the factors that
actually moved this applicant's score, in log-odds, aggregated back to the
feature a human recognises.

Two properties are load-bearing:

* **Faithfulness.** Contributions come from exact TreeSHAP over a design matrix
  of purely numeric splits, so they sum to the model's output. See
  ``ml/training/features.py`` for why that required one-hot encoding.
* **Aggregation.** One-hot columns are summed back to their source feature, so
  the applicant sees "employment type" once rather than five dummy columns.

Signs are normalised so a **positive contribution always means "pushed toward
decline"**, regardless of the underlying feature's direction. This removes an
entire class of reporting bug where a reason code names a factor that was
actually helping the applicant.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
import shap

from ml.explain.feature_dictionary import describe
from ml.training.features import build_design_matrix, source_feature_of

Direction = Literal["adverse", "favourable"]


@dataclass
class ReasonCode:
    rank: int
    feature: str
    label: str
    phrase: str
    contribution: float
    value: Any
    direction: Direction
    actionability: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Explanation:
    applicant_id: str
    probability_of_default: float
    decision: Literal["APPROVE", "DECLINE"]
    threshold: float
    adverse_reasons: list[ReasonCode] = field(default_factory=list)
    favourable_reasons: list[ReasonCode] = field(default_factory=list)
    is_new_to_credit: bool = False

    def to_dict(self) -> dict:
        return {
            "applicant_id": self.applicant_id,
            "probability_of_default": round(self.probability_of_default, 6),
            "decision": self.decision,
            "threshold": round(self.threshold, 6),
            "is_new_to_credit": self.is_new_to_credit,
            "adverse_reasons": [r.to_dict() for r in self.adverse_reasons],
            "favourable_reasons": [r.to_dict() for r in self.favourable_reasons],
        }


class CreditExplainer:
    """Scores an applicant and decomposes the score into reason codes."""

    def __init__(self, bundle: dict) -> None:
        self._estimator = bundle["estimator"]
        self._booster = bundle["raw_estimator"]
        self._features: list[str] = bundle["features"]
        self._threshold: float = bundle["approval_threshold"]
        self._tree_explainer = shap.TreeExplainer(self._booster)

    @classmethod
    def from_artifacts(cls, path: str | Path = "ml/artifacts/model.joblib") -> CreditExplainer:
        return cls(joblib.load(Path(path)))

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def features(self) -> list[str]:
        return list(self._features)

    def predict_proba(self, applicants: pd.DataFrame) -> np.ndarray:
        design = build_design_matrix(applicants, self._features)
        return self._estimator.predict_proba(design)[:, 1]

    def explain(self, applicant: pd.DataFrame, *, top_n: int = 5) -> Explanation:
        """Explain a single applicant.

        Args:
            applicant: a one-row DataFrame of raw features.
            top_n: how many reason codes to return in each direction.
        """
        if len(applicant) != 1:
            raise ValueError(f"explain() takes exactly one applicant row, got {len(applicant)}")

        design = build_design_matrix(applicant, self._features)
        probability = float(self._estimator.predict_proba(design)[0, 1])
        decision: Literal["APPROVE", "DECLINE"] = (
            "APPROVE" if probability <= self._threshold else "DECLINE"
        )

        shap_values = np.asarray(self._tree_explainer.shap_values(design))[0]

        # Aggregate one-hot contributions back to the source feature.
        aggregated: dict[str, float] = {}
        for column, contribution in zip(design.columns, shap_values, strict=True):
            source = source_feature_of(column)
            aggregated[source] = aggregated.get(source, 0.0) + float(contribution)

        row = applicant.iloc[0]
        adverse: list[ReasonCode] = []
        favourable: list[ReasonCode] = []

        for feature, contribution in sorted(
            aggregated.items(), key=lambda kv: abs(kv[1]), reverse=True
        ):
            meaning = describe(feature)
            raw_value = row.get(feature)
            value = None if pd.isna(raw_value) else (
                float(raw_value) if isinstance(raw_value, (int, float, np.number)) else str(raw_value)
            )
            # Positive SHAP raises the log-odds of default, i.e. pushes to decline.
            is_adverse = contribution > 0
            code = ReasonCode(
                rank=0,
                feature=feature,
                label=meaning.label,
                phrase=meaning.adverse_phrase if is_adverse else meaning.favourable_phrase,
                contribution=round(float(contribution), 6),
                value=value,
                direction="adverse" if is_adverse else "favourable",
                actionability=str(meaning.actionability),
            )
            (adverse if is_adverse else favourable).append(code)

        for rank, code in enumerate(adverse[:top_n], start=1):
            code.rank = rank
        for rank, code in enumerate(favourable[:top_n], start=1):
            code.rank = rank

        return Explanation(
            applicant_id=str(row.get("applicant_id", "UNKNOWN")),
            probability_of_default=probability,
            decision=decision,
            threshold=self._threshold,
            adverse_reasons=adverse[:top_n],
            favourable_reasons=favourable[:top_n],
            is_new_to_credit=bool(row.get("is_new_to_credit", 0)),
        )
