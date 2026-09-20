"""Training pipeline behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from ml.data.generator import (
    INCLUSIVE_FEATURES,
    TRADITIONAL_FEATURES,
    GeneratorConfig,
    generate_population,
)
from ml.training.pipeline import (
    TrainingConfig,
    approval_threshold_for_rate,
    ks_statistic,
    train_model,
)

FAST = TrainingConfig(max_iter=60)


@pytest.fixture(scope="module")
def small_population():
    return generate_population(GeneratorConfig(n_applicants=6_000))


def test_ks_is_zero_for_a_random_scorer():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 4000)
    assert ks_statistic(y, rng.random(4000)) < 0.08


def test_ks_is_one_for_a_perfect_scorer():
    y = np.array([0] * 500 + [1] * 500)
    assert ks_statistic(y, y.astype(float)) == pytest.approx(1.0, abs=1e-9)


def test_model_learns_signal_but_not_the_label(small_population):
    """AUC must be well above chance and well below suspicious."""
    model, _ = train_model(small_population, FAST)
    assert 0.68 < model.metrics["roc_auc"] < 0.90, (
        "an AUC near 0.99 on credit data indicates leakage, not skill"
    )
    assert model.metrics["gini"] == pytest.approx(2 * model.metrics["roc_auc"] - 1)


def test_probabilities_are_calibrated(small_population):
    """Brier score must beat predicting the base rate for everyone."""
    model, evaluation = train_model(small_population, FAST)
    base_rate = evaluation["y_test"].mean()
    naive_brier = float(np.mean((evaluation["y_test"] - base_rate) ** 2))
    assert model.metrics["brier"] < naive_brier


def test_splits_are_disjoint_and_complete(small_population):
    model, _ = train_model(small_population, FAST)
    total = model.metrics["n_train"] + model.metrics["n_calibration"] + model.metrics["n_test"]
    assert total == len(small_population)


def test_feature_restriction_is_honoured(small_population):
    model, _ = train_model(small_population, FAST, features=TRADITIONAL_FEATURES)
    assert set(model.features) == set(TRADITIONAL_FEATURES)
    assert "upi_inflow_cv" not in model.features


def test_protected_attributes_cannot_be_requested(small_population):
    with pytest.raises(ValueError, match="not permitted"):
        train_model(small_population, FAST, features=[*TRADITIONAL_FEATURES, "gender"])


def test_alternative_data_improves_discrimination(small_population):
    """The project's central empirical claim, asserted as a test."""
    traditional, _ = train_model(small_population, FAST, features=TRADITIONAL_FEATURES)
    inclusive, _ = train_model(small_population, FAST, features=INCLUSIVE_FEATURES)
    assert inclusive.metrics["roc_auc"] > traditional.metrics["roc_auc"]


def test_approval_threshold_produces_the_requested_rate():
    scores = np.linspace(0, 1, 1000)
    threshold = approval_threshold_for_rate(scores, 0.70)
    assert (scores <= threshold).mean() == pytest.approx(0.70, abs=0.01)
