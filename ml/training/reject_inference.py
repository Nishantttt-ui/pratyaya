"""Reject inference: learning from the applicants a past policy turned away.

The problem
-----------
A lender observes repayment only for applicants it *approved*. Everyone who was
declined has no outcome, so the training population is censored by the previous
policy. The model therefore learns "among the people we already accepted, who
defaulted", which is not the question underwriting asks. It is asked to rank
*all* applicants, including the region of the feature space its predecessor
never lent into and about which the data is silent.

This is not a rare edge case. Every credit model trained on a real book has it,
and it is the largest methodological gap in this project's own pipeline.

Why it can be demonstrated properly here
----------------------------------------
On a real portfolio the damage is unmeasurable: you cannot know how the rejected
applicants would have behaved, which is the whole problem. The generated
population does know. That makes it possible to simulate a prior policy, hide
the outcomes it would have hidden, and then measure exactly what was lost and
how much of it a correction recovers - against an oracle that is unattainable in
practice but computable here.

The correction: fuzzy augmentation
----------------------------------
Also called parcelling. Each rejected applicant is scored by the naive model and
then enters training *twice*: once labelled good with weight ``1 - p`` and once
labelled bad with weight ``p``. The applicant contributes their features to the
fit in proportion to how risky they are believed to be, rather than being
dropped or assigned a hard label the data cannot support.

A ``bad_rate_multiplier`` above 1.0 encodes the standard industry assumption
that rejects are worse than a model trained only on accepts believes, since that
model has never seen an outcome from the region they occupy. The multiplier is a
judgement, not a measurement, so it is a parameter here rather than a constant,
and the experiment sweeps it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from ml.training.features import build_design_matrix


@dataclass
class PriorPolicy:
    """A previous underwriting policy, and the censoring it produced."""

    approved: np.ndarray          # boolean mask over the training rows
    approval_rate: float
    observed_bad_rate: float      # what the lender's book appears to show
    true_bad_rate: float          # what the whole applicant pool actually was


def simulate_prior_policy(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    *,
    approval_rate: float = 0.6,
    seed: int = 20260921,
) -> PriorPolicy:
    """Approve the safest-looking share of applicants, using limited evidence.

    The stand-in for a legacy scorecard is a shallow model on a restricted
    feature set. That is deliberate: a prior policy that was already as good as
    the model we are trying to build would leave nothing to recover, and would
    make the experiment look better than it is.
    """
    rng = np.random.default_rng(seed)
    design = build_design_matrix(frame, features)
    y = frame[target].to_numpy().astype(int)

    legacy = HistGradientBoostingClassifier(
        max_iter=40, max_depth=3, learning_rate=0.1, random_state=seed
    ).fit(design, y)
    scores = legacy.predict_proba(design)[:, 1]

    # Real underwriting is not a clean cut on a score: policy overrides, manual
    # review and inconsistency all blur the boundary, so jitter it.
    scores = scores + rng.normal(0, scores.std() * 0.25, len(scores))
    cutoff = np.quantile(scores, approval_rate)
    approved = scores <= cutoff

    return PriorPolicy(
        approved=approved,
        approval_rate=float(approved.mean()),
        observed_bad_rate=float(y[approved].mean()),
        true_bad_rate=float(y.mean()),
    )


def fit_naive(train: pd.DataFrame, features: list[str], target: str, seed: int = 20260921):
    """What a lender actually does: train on the accepted book alone."""
    return HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, min_samples_leaf=40,
        l2_regularization=1.0, early_stopping=True, random_state=seed,
    ).fit(build_design_matrix(train, features), train[target].to_numpy().astype(int))


def fit_with_reject_inference(
    accepted: pd.DataFrame,
    rejected: pd.DataFrame,
    features: list[str],
    target: str,
    *,
    bad_rate_multiplier: float = 1.0,
    seed: int = 20260921,
):
    """Fuzzy augmentation: rejects enter twice, weighted by inferred risk."""
    naive = fit_naive(accepted, features, target, seed)

    accepted_design = build_design_matrix(accepted, features)
    rejected_design = build_design_matrix(rejected, features)

    p_bad = naive.predict_proba(rejected_design)[:, 1]
    p_bad = np.clip(p_bad * bad_rate_multiplier, 0.0, 1.0)

    design = pd.concat([accepted_design, rejected_design, rejected_design], ignore_index=True)
    labels = np.concatenate([
        accepted[target].to_numpy().astype(int),
        np.ones(len(rejected), dtype=int),    # the "went bad" copy
        np.zeros(len(rejected), dtype=int),   # the "repaid" copy
    ])
    weights = np.concatenate([
        np.ones(len(accepted)),
        p_bad,
        1.0 - p_bad,
    ])

    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, min_samples_leaf=40,
        l2_regularization=1.0, early_stopping=True, random_state=seed,
    )
    model.fit(design, labels, sample_weight=weights)
    return model


def fit_oracle(train: pd.DataFrame, features: list[str], target: str, seed: int = 20260921):
    """Trained on every applicant, rejected ones included.

    Unattainable on a real book - the outcomes simply do not exist - but
    computable here, and it is the only honest upper bound for how much reject
    inference could recover.
    """
    return fit_naive(train, features, target, seed)
