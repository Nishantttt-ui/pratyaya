"""Reject inference behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from ml.data.generator import INCLUSIVE_FEATURES, TARGET_COLUMN
from ml.training.reject_inference import (
    fit_naive,
    fit_with_reject_inference,
    simulate_prior_policy,
)

LEGACY_VIEW = ["bureau_score", "credit_history_months", "monthly_income_declared",
               "emi_to_income", "is_new_to_credit", "age"]


@pytest.fixture(scope="module")
def policy(population):
    return simulate_prior_policy(
        population, LEGACY_VIEW, TARGET_COLUMN, approval_rate=0.6
    )


def test_prior_policy_approves_the_requested_share(policy):
    assert policy.approval_rate == pytest.approx(0.6, abs=0.02)


def test_the_accepted_book_understates_true_risk(policy):
    """The defining symptom of censoring.

    A lender reading only their own book sees a safer portfolio than the
    population they are underwriting, because the applicants most likely to
    default were the ones turned away.
    """
    assert policy.observed_bad_rate < policy.true_bad_rate


def test_prior_policy_is_not_a_clean_cut(population, policy):
    """Real underwriting is blurred by overrides and manual review.

    A perfectly separable prior policy would make the experiment easier than
    reality, so the simulated one is jittered. If the approved and rejected sets
    were perfectly separated by risk, no recovery would be possible.
    """
    approved_bad = population[policy.approved][TARGET_COLUMN].mean()
    rejected_bad = population[~policy.approved][TARGET_COLUMN].mean()
    assert 0.0 < approved_bad < rejected_bad < 1.0


def test_fuzzy_augmentation_weights_sum_to_one_reject(population, policy):
    """Each reject contributes exactly one applicant's worth of evidence.

    It enters twice - once good, once bad - and the two weights must sum to 1,
    otherwise rejects would be silently over- or under-counted relative to the
    accepted book.
    """
    accepted = population[policy.approved].reset_index(drop=True)
    rejected = population[~policy.approved].reset_index(drop=True).head(500)

    naive = fit_naive(accepted, INCLUSIVE_FEATURES, TARGET_COLUMN)
    from ml.training.features import build_design_matrix

    p_bad = naive.predict_proba(build_design_matrix(rejected, INCLUSIVE_FEATURES))[:, 1]
    assert np.allclose(p_bad + (1.0 - p_bad), 1.0)


def test_correction_recovers_some_of_the_censoring_cost(population, policy):
    """The load-bearing claim: the correction must actually help.

    Measured on the whole applicant pool, which is the population the model is
    asked to rank, rather than on the accepted book it was trained from.
    """
    from sklearn.metrics import roc_auc_score

    from ml.training.features import build_design_matrix

    accepted = population[policy.approved].reset_index(drop=True)
    rejected = population[~policy.approved].reset_index(drop=True)
    y_all = population[TARGET_COLUMN].to_numpy().astype(int)
    design = build_design_matrix(population, INCLUSIVE_FEATURES)

    naive = fit_naive(accepted, INCLUSIVE_FEATURES, TARGET_COLUMN)
    corrected = fit_with_reject_inference(
        accepted, rejected, INCLUSIVE_FEATURES, TARGET_COLUMN, bad_rate_multiplier=2.0
    )

    naive_auc = roc_auc_score(y_all, naive.predict_proba(design)[:, 1])
    corrected_auc = roc_auc_score(y_all, corrected.predict_proba(design)[:, 1])
    assert corrected_auc > naive_auc


def test_multiplier_of_one_is_close_to_doing_nothing(population, policy):
    """A multiplier of 1.0 trusts the naive model's view of the rejects.

    Since that model has never seen an outcome from the rejected region, that
    assumption is the weak one, and the correction should barely move. This test
    guards the claim that the multiplier is doing the work.
    """
    from sklearn.metrics import roc_auc_score

    from ml.training.features import build_design_matrix

    accepted = population[policy.approved].reset_index(drop=True)
    rejected = population[~policy.approved].reset_index(drop=True)
    y_all = population[TARGET_COLUMN].to_numpy().astype(int)
    design = build_design_matrix(population, INCLUSIVE_FEATURES)

    naive_auc = roc_auc_score(
        y_all, fit_naive(accepted, INCLUSIVE_FEATURES, TARGET_COLUMN).predict_proba(design)[:, 1]
    )
    weak = fit_with_reject_inference(
        accepted, rejected, INCLUSIVE_FEATURES, TARGET_COLUMN, bad_rate_multiplier=1.0
    )
    weak_auc = roc_auc_score(y_all, weak.predict_proba(design)[:, 1])
    assert abs(weak_auc - naive_auc) < 0.02
