"""The design matrix: the exact, stable contract between data and model.

Why one-hot instead of native categorical splits
------------------------------------------------
``HistGradientBoostingClassifier`` can split on pandas categorical columns
directly, which is more compact and marginally more accurate. We deliberately
do not use that here.

The reason is explainability, not performance. SHAP's ``TreeExplainer`` walks a
tree assuming every split is a numeric threshold. When the booster splits a
categorical by set membership instead, TreeSHAP mis-attributes the contribution
and the resulting values no longer sum to the model's output. Measured on this
model, that additivity error reached 0.24 in log-odds - large enough to reorder
which factors appear in an applicant's reason codes.

A reason code that does not faithfully reflect what the model did is worse than
no reason code at all: under the RBI Fair Practices Code the lender must convey
the actual reason for rejection, so a plausible-sounding but unfaithful
explanation is a compliance failure dressed up as transparency.

One-hot encoding makes every split numeric, which makes TreeSHAP exact. The
additivity property is asserted in ``backend/tests/unit/test_explainability.py``
so it cannot silently regress. Missing numeric values are still passed through
as NaN and handled natively by the booster - that behaviour is unchanged, and it
is what lets a new-to-credit applicant be scored without a fabricated bureau
score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Fixed vocabularies. Pinning these guarantees that the design matrix has the
# same columns in the same order at training time and at serving time, which is
# the usual source of silent train/serve skew.
CATEGORICAL_VOCAB: dict[str, list[str]] = {
    "education": ["upto_secondary", "higher_secondary", "graduate", "postgraduate"],
    "employment_type": ["salaried_formal", "salaried_informal", "self_employed", "gig_worker", "agri"],
    "loan_purpose": ["consumer_durable", "education", "medical", "business_working_capital", "two_wheeler"],
}


def design_columns(features: list[str]) -> list[str]:
    """Column names of the design matrix produced from ``features``."""
    columns: list[str] = []
    for feature in features:
        if feature in CATEGORICAL_VOCAB:
            columns.extend(f"{feature}={level}" for level in CATEGORICAL_VOCAB[feature])
        else:
            columns.append(feature)
    return columns


def build_design_matrix(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Expand raw features into the numeric design matrix the model consumes.

    Categorical columns become one-hot indicators over a pinned vocabulary.
    Numeric columns pass through untouched, NaN included.
    """
    blocks: dict[str, np.ndarray] = {}
    for feature in features:
        if feature in CATEGORICAL_VOCAB:
            values = frame[feature].astype(str).to_numpy()
            for level in CATEGORICAL_VOCAB[feature]:
                blocks[f"{feature}={level}"] = (values == level).astype(float)
        else:
            blocks[feature] = pd.to_numeric(frame[feature], errors="coerce").to_numpy(dtype=float)

    matrix = pd.DataFrame(blocks, index=frame.index)
    return matrix[design_columns(features)]


def source_feature_of(design_column: str) -> str:
    """Map a design column back to the raw feature it came from.

    ``"employment_type=gig_worker"`` maps to ``"employment_type"``. Used when
    aggregating one-hot contributions back to a single reason code.
    """
    return design_column.split("=", 1)[0]
