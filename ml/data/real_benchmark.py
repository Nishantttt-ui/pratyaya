"""Real public credit datasets, used to validate the modelling pipeline.

Why this exists
---------------
The applicant population in ``ml/data/generator.py`` is synthetic, and the
obvious objection is that the results could be an artefact of assumptions baked
into the generator. This module answers that objection directly: the *same*
pipeline - one-hot design matrix, histogram gradient boosting, isotonic
calibration, exact TreeSHAP, and the fairness audit - is run over two real,
public credit datasets with real observed defaults.

What that does and does not prove:

* It **does** show the machinery is sound on genuine credit data: that it
  reaches discrimination comparable to published results, that the probabilities
  calibrate, that TreeSHAP stays exact, and that the fairness audit produces
  sensible numbers against a real protected attribute.
* It **does not** transfer the inclusion finding. Neither dataset contains
  Account Aggregator-style alternative data, so the traditional-versus-inclusive
  comparison cannot be reproduced here. That claim rests on the synthetic
  population, and the README says so.

Datasets
--------
**German Credit** (Statlog, via OpenML ``credit-g``) - 1,000 applicants, the
canonical benchmark in the algorithmic-fairness literature. Gender is recoverable
from the ``personal_status`` field.

**Taiwan Default of Credit Card Clients** (via OpenML) - 30,000 accounts with
observed default in the following month, and an explicit sex attribute. Roughly
the same size as our synthetic population, which makes the comparison fair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Benchmark:
    """A real dataset, prepared for the project's pipeline."""

    name: str
    source: str
    frame: pd.DataFrame
    features: list[str]
    target: str
    protected: list[str]
    vocab: dict[str, list[str]] = field(default_factory=dict)

    @property
    def base_rate(self) -> float:
        return float(self.frame[self.target].mean())


def _vocab_from(frame: pd.DataFrame, columns: list[str]) -> dict[str, list[str]]:
    """Pin each categorical column's observed levels, sorted for stability."""
    return {c: sorted(frame[c].astype(str).unique().tolist()) for c in columns}


def load_german_credit() -> Benchmark:
    """Statlog German Credit, 1,000 applicants."""
    from sklearn.datasets import fetch_openml

    raw = fetch_openml("credit-g", version=1, as_frame=True, parser="auto").frame.copy()

    # personal_status encodes marital status and sex together; sex alone is the
    # protected attribute, so it is split out and the combined field dropped.
    status = raw["personal_status"].astype(str)
    raw["sex"] = np.where(status.str.contains("female"), "female", "male")
    raw = raw.drop(columns=["personal_status"])

    # OpenML labels the target "good"/"bad" credit risk; 1 = bad, to match the
    # convention used everywhere else in this project (1 = default).
    raw["default"] = (raw["class"].astype(str) == "bad").astype(int)
    raw = raw.drop(columns=["class"])

    protected = ["sex", "age_band"]
    raw["age_band"] = pd.cut(
        raw["age"].astype(float), bins=[18, 30, 40, 50, 100],
        labels=["19-30", "31-40", "41-50", "51+"],
    ).astype(str)

    features = [c for c in raw.columns if c not in {"default", *protected}]
    categoricals = [
        c for c in features
        if raw[c].dtype == object or str(raw[c].dtype) == "category"
    ]

    return Benchmark(
        name="German Credit (Statlog)",
        source="OpenML credit-g, version 1",
        frame=raw,
        features=features,
        target="default",
        protected=protected,
        vocab=_vocab_from(raw, categoricals),
    )


def load_taiwan_default() -> Benchmark:
    """Default of Credit Card Clients (Taiwan), 30,000 accounts."""
    from sklearn.datasets import fetch_openml

    raw = fetch_openml(
        "default-of-credit-card-clients", version=1, as_frame=True, parser="auto"
    ).frame.copy()

    # OpenML serves this with positional names (x1..x23, y). The mapping below
    # is from the dataset's own documentation.
    names = {
        "x1": "credit_limit", "x2": "sex", "x3": "education", "x4": "marriage", "x5": "age",
        "x6": "repay_status_1", "x7": "repay_status_2", "x8": "repay_status_3",
        "x9": "repay_status_4", "x10": "repay_status_5", "x11": "repay_status_6",
        "x12": "bill_amt_1", "x13": "bill_amt_2", "x14": "bill_amt_3",
        "x15": "bill_amt_4", "x16": "bill_amt_5", "x17": "bill_amt_6",
        "x18": "pay_amt_1", "x19": "pay_amt_2", "x20": "pay_amt_3",
        "x21": "pay_amt_4", "x22": "pay_amt_5", "x23": "pay_amt_6",
        "y": "default",
    }
    raw = raw.rename(columns=names)
    for column in raw.columns:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")

    raw["default"] = raw["default"].astype(int)
    raw["sex"] = np.where(raw["sex"] == 2, "female", "male")   # 1 = male, 2 = female
    raw["age_band"] = pd.cut(
        raw["age"], bins=[20, 30, 40, 50, 100], labels=["21-30", "31-40", "41-50", "51+"]
    ).astype(str)

    protected = ["sex", "age_band"]
    features = [c for c in raw.columns if c not in {"default", *protected}]

    return Benchmark(
        name="Taiwan Default of Credit Card Clients",
        source="OpenML default-of-credit-card-clients, version 1",
        frame=raw,
        features=features,
        target="default",
        protected=protected,
        vocab={},   # every retained feature is numeric
    )


# --- Feature families for the partial replication -------------------------
# Taiwan's columns divide naturally into the two kinds of evidence this project
# contrasts. The repayment-status columns are a delinquency record: the same
# kind of information a credit bureau holds. The billing and payment amounts are
# observed cash-flow behaviour, which is what alternative data supplies. That
# makes it possible to run the accuracy half of the inclusion experiment on real
# defaults rather than on generated ones.
TAIWAN_BUREAU_LIKE = [
    "credit_limit", "age", "education", "marriage",
    *[f"repay_status_{i}" for i in range(1, 7)],
]
TAIWAN_BEHAVIOURAL = [
    *[f"bill_amt_{i}" for i in range(1, 7)],
    *[f"pay_amt_{i}" for i in range(1, 7)],
]


def load_all() -> list[Benchmark]:
    return [load_german_credit(), load_taiwan_default()]
