"""Recourse must be actionable, attainable and real."""

from __future__ import annotations

from ml.explain.feature_dictionary import Actionability, describe, is_actionable
from ml.explain.recourse import find_recourse


def test_immutable_attributes_are_never_actionable():
    for feature in ("age", "education"):
        assert not is_actionable(feature)
        assert describe(feature).actionability is Actionability.FIXED


def test_derived_features_are_not_offered_as_recourse():
    """'Lower your instalment-to-income ratio' is not an action.

    The actions are 'borrow less' and 'repay over longer', which are offered
    separately as loan_amount_requested and loan_tenure_months.
    """
    assert describe("emi_to_income").is_derived
    assert not is_actionable("emi_to_income")


def test_behavioural_signals_are_actionable():
    for feature in ("days_balance_below_500", "utility_ontime_ratio", "loan_amount_requested"):
        assert is_actionable(feature)


def test_approved_applicants_receive_no_recourse(population, explainer):
    probabilities = explainer.predict_proba(population)
    approved = population[probabilities <= explainer.threshold].head(1)
    assert find_recourse(approved, explainer=explainer, population=population) == []


def test_recourse_options_actually_flip_the_decision(population, explainer):
    """Every option must be verified against the real model, not asserted."""
    probabilities = explainer.predict_proba(population)
    declined = population[probabilities > explainer.threshold].head(3)

    checked = 0
    for i in range(len(declined)):
        row = declined.iloc[[i]]
        for option in find_recourse(row, explainer=explainer, population=population):
            counterfactual = row.copy()
            counterfactual[option.feature] = option.target_value
            if option.feature == "loan_amount_requested":
                counterfactual["emi_to_income"] = min(max(
                    (option.target_value * 1.17 / counterfactual["loan_tenure_months"].iloc[0])
                    / max(counterfactual["monthly_income_declared"].iloc[0], 1), 0.01), 5.0)
            elif option.feature == "loan_tenure_months":
                counterfactual["emi_to_income"] = min(max(
                    (counterfactual["loan_amount_requested"].iloc[0] * 1.17 / max(option.target_value, 1))
                    / max(counterfactual["monthly_income_declared"].iloc[0], 1), 0.01), 5.0)
            assert explainer.predict_proba(counterfactual)[0] <= explainer.threshold + 1e-9
            checked += 1
    assert checked > 0, "expected at least one recourse option to verify"


def test_targets_stay_within_the_attainable_range(population, explainer):
    """No advice may require exceeding the 85th percentile of the population."""
    probabilities = explainer.predict_proba(population)
    declined = population[probabilities > explainer.threshold].head(5)

    for i in range(len(declined)):
        row = declined.iloc[[i]]
        for option in find_recourse(row, explainer=explainer, population=population):
            series = population[option.feature].dropna()
            lower, upper = series.quantile(0.15), series.quantile(0.85)
            assert lower - 1e-6 <= option.target_value <= upper + 1e-6, (
                f"{option.feature} target {option.target_value} outside attainable band"
            )
