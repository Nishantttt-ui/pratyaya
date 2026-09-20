"""Explainability invariants.

The additivity test here is the most important test in the suite. An earlier
version of this model split on pandas categoricals natively, which made
TreeSHAP's attributions unfaithful by up to 0.24 in log-odds - enough to
reorder an applicant's reason codes. Under the RBI Fair Practices Code the
lender must convey the actual reason for rejection, so unfaithful reason codes
are a compliance failure rather than a cosmetic one. This test is what stops
that regressing silently.
"""

from __future__ import annotations

import numpy as np
import pytest
import shap

from ml.training.features import build_design_matrix, design_columns, source_feature_of


def test_design_matrix_is_entirely_numeric(population, explainer):
    matrix = build_design_matrix(population.head(200), explainer.features)
    assert all(np.issubdtype(dtype, np.floating) for dtype in matrix.dtypes)


def test_design_matrix_preserves_missing_bureau_values(population, explainer):
    """NaN must survive into the model rather than being imputed."""
    ntc = population[population["is_new_to_credit"] == 1].head(50)
    matrix = build_design_matrix(ntc, explainer.features)
    assert matrix["bureau_score"].isna().all()


def test_design_matrix_column_order_is_stable(explainer):
    a = design_columns(explainer.features)
    b = design_columns(explainer.features)
    assert a == b, "column order must be deterministic to avoid train/serve skew"


def test_shap_values_sum_to_the_model_output(population, explainer):
    """Exact additivity. This is the invariant the one-hot refactor bought."""
    sample = population.head(150)
    matrix = build_design_matrix(sample, explainer.features)
    booster = explainer._booster  # noqa: SLF001 - deliberate white-box assertion

    tree_explainer = shap.TreeExplainer(booster)
    values = np.asarray(tree_explainer.shap_values(matrix))
    base = float(np.ravel(tree_explainer.expected_value)[0])

    reconstructed = base + values.sum(axis=1)
    actual = booster.decision_function(matrix)
    assert np.max(np.abs(reconstructed - actual)) < 1e-6


def test_one_hot_columns_map_back_to_their_source_feature():
    assert source_feature_of("employment_type=gig_worker") == "employment_type"
    assert source_feature_of("bureau_score") == "bureau_score"


def test_explanation_contains_no_protected_attribute(population, explainer):
    """Gender and region must not appear as reasons; the model never saw them."""
    row = population.head(1)
    explanation = explainer.explain(row)
    named = {r.feature for r in explanation.adverse_reasons + explanation.favourable_reasons}
    assert not named & {"gender", "region_tier", "age_band"}


def test_adverse_and_favourable_signs_are_consistent(population, explainer):
    """Positive contribution must always mean 'pushed toward decline'."""
    row = population.head(1)
    explanation = explainer.explain(row, top_n=8)
    assert all(r.contribution > 0 for r in explanation.adverse_reasons)
    assert all(r.contribution < 0 for r in explanation.favourable_reasons)


def test_decision_matches_threshold_comparison(population, explainer):
    sample = population.head(60)
    probabilities = explainer.predict_proba(sample)
    for i in range(len(sample)):
        explanation = explainer.explain(sample.iloc[[i]])
        expected = "APPROVE" if probabilities[i] <= explainer.threshold else "DECLINE"
        assert explanation.decision == expected


def test_explain_rejects_multiple_rows(population, explainer):
    with pytest.raises(ValueError, match="exactly one applicant"):
        explainer.explain(population.head(3))
