"""The generator's guarantees.

These tests defend the claims the whole fairness argument rests on. If the
seeded population stopped having equal true risk across groups, the headline
result would silently become meaningless rather than failing loudly.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.data.generator import (
    INCLUSIVE_FEATURES,
    PROTECTED_ATTRIBUTES,
    TARGET_COLUMN,
    feature_columns,
)


def test_protected_attributes_are_never_model_features(population):
    features = feature_columns(population)
    for attribute in PROTECTED_ATTRIBUTES:
        assert attribute not in features
    assert "applicant_id" not in features
    assert TARGET_COLUMN not in features


def test_feature_families_exactly_cover_the_model_surface(population):
    assert set(feature_columns(population)) == set(INCLUSIVE_FEATURES)


def test_no_single_feature_proxies_the_target(population):
    """Guards against the classic synthetic-data failure of a leaked label."""
    numeric = population[feature_columns(population)].select_dtypes("number")
    correlations = numeric.corrwith(population[TARGET_COLUMN]).abs()
    assert correlations.max() < 0.60, f"possible leakage via {correlations.idxmax()}"


def test_default_rate_is_near_the_configured_target(population):
    assert population[TARGET_COLUMN].mean() == pytest.approx(0.12, abs=0.02)


@pytest.mark.parametrize("attribute", ["gender", "region_tier"])
def test_true_risk_is_equal_across_protected_groups(population, attribute):
    """The load-bearing assumption.

    Default is generated from latent capacity and willingness only, with no
    gender or region term. Any approval disparity a model then produces is
    unjustified by risk - which is what makes the fairness result meaningful.
    """
    rates = population.groupby(attribute, observed=True)[TARGET_COLUMN].mean()
    assert rates.max() - rates.min() < 0.025


def test_availability_bias_is_present_as_designed(population):
    """Women and rural applicants are more often new-to-credit."""
    by_gender = population.groupby("gender", observed=True)["is_new_to_credit"].mean()
    assert by_gender["female"] > by_gender["male"] + 0.10

    rural = population["region_tier"].isin(["tier3", "rural"])
    assert (
        population.loc[rural, "is_new_to_credit"].mean()
        > population.loc[~rural, "is_new_to_credit"].mean() + 0.08
    )


def test_income_declaration_bias_is_present_as_designed(population):
    medians = population.groupby("gender", observed=True)["monthly_income_declared"].median()
    assert medians["female"] < medians["male"]


def test_bias_can_be_switched_off(fair_population):
    """With both mechanisms disabled the groups become observationally similar.

    This is what lets the fairness audit be tested for false positives: it must
    report no disparity when the data contains none.
    """
    by_gender = fair_population.groupby("gender", observed=True)["is_new_to_credit"].mean()
    assert abs(by_gender["female"] - by_gender["male"]) < 0.05

    medians = fair_population.groupby("gender", observed=True)["monthly_income_declared"].median()
    assert medians["female"] == pytest.approx(medians["male"], rel=0.10)


def test_new_to_credit_applicants_have_no_bureau_record(population):
    """Missingness must be genuine, not imputed away at generation time."""
    ntc = population[population["is_new_to_credit"] == 1]
    assert ntc["bureau_score"].isna().all()
    assert ntc["credit_history_months"].isna().all()

    established = population[population["is_new_to_credit"] == 0]
    assert established["bureau_score"].notna().all()


def test_generation_is_reproducible():
    from ml.data.generator import GeneratorConfig, generate_population

    a = generate_population(GeneratorConfig(n_applicants=500, seed=42))
    b = generate_population(GeneratorConfig(n_applicants=500, seed=42))
    assert np.array_equal(a[TARGET_COLUMN].to_numpy(), b[TARGET_COLUMN].to_numpy())
