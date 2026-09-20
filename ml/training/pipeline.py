"""Training and evaluation for the credit decisioning model.

Model choice
------------
``HistGradientBoostingClassifier``. Two properties matter for this problem:

* **Native NaN handling.** For thin-file applicants a missing bureau score is
  not a data-quality defect to be imputed away - it is the defining fact about
  them. Imputing a median bureau score would fabricate a credit history that
  does not exist and would quietly erase the signal. This booster learns an
  explicit default direction for missing values at each split instead.
* **Native categorical support**, so employment type and loan purpose are split
  on directly rather than one-hot expanded.

It is also pure Python + scikit-learn with no compiled system dependency, so
the project installs on a clean machine. LightGBM and XGBoost both dynamically
link ``libomp`` on macOS, which is absent unless the grader has Homebrew.

Calibration
-----------
A credit model must output probabilities that *mean* something: if the model
says 8%, roughly 8 in 100 such applicants should default, because pricing and
provisioning are computed from that number. Raw boosted-tree scores are not
well calibrated, so the classifier is wrapped in isotonic calibration fitted on
a held-out split, and the Brier score and calibration curve are reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from ml.data.generator import TARGET_COLUMN, feature_columns
from ml.training.features import build_design_matrix, design_columns

CATEGORICAL_COLUMNS = ["education", "employment_type", "loan_purpose"]


@dataclass
class TrainingConfig:
    test_size: float = 0.25
    calibration_size: float = 0.20
    seed: int = 20260921
    max_iter: int = 400
    learning_rate: float = 0.06
    max_leaf_nodes: int = 31
    min_samples_leaf: int = 40
    l2_regularization: float = 1.0
    early_stopping: bool = True


@dataclass
class TrainedModel:
    """A fitted model plus everything needed to explain and audit it."""

    estimator: Any                      # calibrated classifier used for scoring
    raw_estimator: Any                  # uncalibrated booster, used by TreeSHAP
    features: list[str]
    categorical_columns: list[str]
    metrics: dict[str, float] = field(default_factory=dict)
    design_columns: list[str] = field(default_factory=list)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        """Score raw applicant rows, building the design matrix internally."""
        return self.estimator.predict_proba(prepare_frame(frame, self.features))[:, 1]


def prepare_frame(
    frame: pd.DataFrame, features: list[str], vocab: dict[str, list[str]] | None = None
) -> pd.DataFrame:
    """Build the numeric design matrix the booster and TreeSHAP both consume."""
    return build_design_matrix(frame, features, vocab)


def ks_statistic(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Kolmogorov-Smirnov separation, the standard credit-risk ranking metric.

    It is the largest gap between the cumulative distributions of scores for
    defaulters and non-defaulters. Credit teams quote KS far more often than
    AUC, so reporting it makes the results legible to a risk audience.
    """
    order = np.argsort(y_score)
    y = np.asarray(y_true)[order]
    positives = np.cumsum(y) / max(y.sum(), 1)
    negatives = np.cumsum(1 - y) / max((1 - y).sum(), 1)
    return float(np.max(np.abs(positives - negatives)))


def expected_calibration_error(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10) -> float:
    """Average gap between predicted and observed default rate, by score bin.

    Credit pricing and provisioning are computed from the probability, so it
    has to mean what it says: among applicants scored at 8%, roughly 8 in 100
    should default. Bins are equal-population rather than equal-width, so a
    sparsely populated tail cannot dominate the statistic.
    """
    y_true = np.asarray(y_true).astype(float)
    y_score = np.asarray(y_score, dtype=float)
    edges = np.quantile(y_score, np.linspace(0, 1, n_bins + 1))
    edges[-1] += 1e-9
    error = 0.0
    for i in range(n_bins):
        mask = (y_score >= edges[i]) & (y_score < edges[i + 1])
        if not mask.any():
            continue
        error += (mask.sum() / len(y_score)) * abs(y_score[mask].mean() - y_true[mask].mean())
    return float(error)


def train_model(
    frame: pd.DataFrame,
    config: TrainingConfig | None = None,
    features: list[str] | None = None,
    target: str | None = None,
    vocab: dict[str, list[str]] | None = None,
) -> tuple[TrainedModel, dict]:
    """Fit the decisioning model and return it with a held-out evaluation.

    Args:
        frame: the applicant population.
        config: hyperparameters and split sizes.
        features: restrict training to this feature subset. Used to compare
            traditional bureau-only underwriting against underwriting that also
            sees consented alternative data. Defaults to every permitted
            feature. Protected attributes are excluded regardless.
        target: the outcome column. Defaults to this project's own target.
        vocab: categorical vocabulary for the design matrix. Supplying both
            ``target`` and ``vocab`` is what lets this identical pipeline run
            over an external benchmark dataset - see
            ``scripts/validate_on_real_data.py``. When they are supplied the
            caller owns feature selection, so the project's own
            protected-attribute guard does not apply and the caller must
            exclude them itself.
    """
    cfg = config or TrainingConfig()
    external = target is not None
    target = target or TARGET_COLUMN

    if external:
        if features is None:
            raise ValueError("an external dataset must state its features explicitly")
    else:
        allowed = feature_columns(frame)
        if features is None:
            features = allowed
        else:
            illegal = set(features) - set(allowed)
            if illegal:
                raise ValueError(f"Features not permitted for training: {sorted(illegal)}")
            features = [f for f in features if f in allowed]
    X = prepare_frame(frame, features, vocab)
    design = design_columns(features, vocab)
    y = frame[target].to_numpy().astype(int)

    # Three-way split: fit / calibrate / test. Calibration must not see the
    # test set, and the booster must not see the calibration set.
    X_fit_cal, X_test, y_fit_cal, y_test, idx_fit_cal, idx_test = train_test_split(
        X, y, np.arange(len(frame)), test_size=cfg.test_size, stratify=y, random_state=cfg.seed
    )
    X_fit, X_cal, y_fit, y_cal = train_test_split(
        X_fit_cal, y_fit_cal, test_size=cfg.calibration_size, stratify=y_fit_cal, random_state=cfg.seed
    )

    booster = HistGradientBoostingClassifier(
        max_iter=cfg.max_iter,
        learning_rate=cfg.learning_rate,
        max_leaf_nodes=cfg.max_leaf_nodes,
        min_samples_leaf=cfg.min_samples_leaf,
        l2_regularization=cfg.l2_regularization,
        early_stopping=cfg.early_stopping,
        validation_fraction=0.15,
        random_state=cfg.seed,
    )
    booster.fit(X_fit, y_fit)

    # Isotonic calibration on the untouched calibration split. The booster is
    # wrapped in FrozenEstimator so calibration fits only the isotonic mapping
    # and leaves the fitted trees alone. (This replaces cv="prefit", which was
    # removed in scikit-learn 1.8.)
    calibrated = CalibratedClassifierCV(FrozenEstimator(booster), method="isotonic")
    calibrated.fit(X_cal, y_cal)

    p_test = calibrated.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, p_test)
    metrics = {
        "roc_auc": float(auc),
        "gini": float(2 * auc - 1),
        "ks": ks_statistic(y_test, p_test),
        "pr_auc": float(average_precision_score(y_test, p_test)),
        "brier": float(brier_score_loss(y_test, p_test)),
        "base_rate": float(y_test.mean()),
        "n_train": int(len(X_fit)),
        "n_calibration": int(len(X_cal)),
        "n_test": int(len(X_test)),
    }

    model = TrainedModel(
        estimator=calibrated,
        raw_estimator=booster,
        features=features,
        categorical_columns=[c for c in CATEGORICAL_COLUMNS if c in features],
        metrics=metrics,
        design_columns=design,
    )

    evaluation = {
        "metrics": metrics,
        "test_index": idx_test,
        "y_test": y_test,
        "p_test": p_test,
        "X_test": X_test,
    }
    return model, evaluation


def approval_threshold_for_rate(p_scores: np.ndarray, approval_rate: float) -> float:
    """Probability-of-default cutoff that approves the given share of applicants.

    Lending policy is usually expressed as an approval rate the business can
    fund, rather than an abstract probability cutoff, so the threshold is
    derived from that rate.
    """
    return float(np.quantile(p_scores, approval_rate))
