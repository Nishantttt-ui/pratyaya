"""Algorithmic bias-mitigation strategies, compared against the data-driven fix.

This project's central claim is that the disparity in thin-file lending is a
property of the *evidence* rather than of the algorithm, and that widening the
evidence - adding consented alternative data - removes it. That claim is only
worth something if the standard algorithmic remedies were actually tried, so
this module runs them.

Four strategies, all measured at an identical approval rate:

* **Baseline** - the booster on the traditional bureau feature set.
* **CorrelationRemover** (pre-processing) - linearly removes each feature's
  correlation with the protected attribute before training.
* **ExponentiatedGradient** (in-processing) - solves a constrained problem,
  reducing the model to a sequence of cost-sensitive fits under a demographic
  parity constraint.
* **ThresholdOptimizer** (post-processing) - derives a separate decision
  threshold per group.

Where the protected attribute is needed matters as much as the score
--------------------------------------------------------------------
A fair-lending remedy that reads an applicant's gender *at decision time* is
applying a different rule to different people, which is the thing fair lending
prohibits rather than a cure for it. The three methods differ sharply here, and
the comparison records it:

* ``ExponentiatedGradient`` needs the attribute only while fitting; ``predict``
  takes features alone.
* ``ThresholdOptimizer`` requires ``sensitive_features`` at predict time by
  construction - the per-group threshold *is* the mechanism.
* ``CorrelationRemover`` requires the sensitive columns at transform time, so a
  deployed scorer would have to collect and read them for every application.

Adding alternative data needs the attribute at neither point.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from ml.training.features import build_design_matrix


@dataclass
class MitigationResult:
    """One strategy's scores on the held-out split."""

    name: str
    family: str
    scores: np.ndarray                 # higher = riskier
    needs_attribute_at_decision: bool
    note: str = ""
    degenerate: bool = False
    diagnostic: str = ""

    def check_degeneracy(self) -> MitigationResult:
        """Flag a strategy that cannot actually be operated.

        A lender chooses an approval rate and needs a score that ranks
        applicants so the cutoff can be placed there. A strategy that emits only
        a handful of distinct values cannot do that: it has one operating point,
        take it or leave it. Reporting an AUC for such a strategy would imply a
        ranking it does not provide, so the comparison marks it instead.
        """
        distinct = int(len(np.unique(np.round(self.scores, 6))))
        if distinct <= 2:
            self.degenerate = True
            self.diagnostic = (
                f"Emits only {distinct} distinct scores, so it cannot be operated at a "
                "chosen approval rate. Any AUC quoted for it would imply a ranking it "
                "does not produce."
            )
        return self


def _booster(seed: int = 20260921) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
        min_samples_leaf=40, l2_regularization=1.0,
        early_stopping=True, validation_fraction=0.15, random_state=seed,
    )


def _orient(scores: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ensure higher means riskier.

    Some fairlearn estimators expose a probability mass function whose column
    order is not guaranteed to match our 1 = default convention, so the
    orientation is checked against the outcome rather than assumed.
    """
    from sklearn.metrics import roc_auc_score

    return scores if roc_auc_score(y, scores) >= 0.5 else -scores


def run_baseline(X_train, y_train, X_test, features, vocab=None) -> MitigationResult:
    model = _booster().fit(build_design_matrix(X_train, features, vocab), y_train)
    scores = model.predict_proba(build_design_matrix(X_test, features, vocab))[:, 1]
    return MitigationResult(
        name="Baseline", family="none", scores=scores, needs_attribute_at_decision=False,
        note="Traditional bureau feature set, no mitigation applied.",
    ).check_degeneracy()


def run_correlation_remover(
    X_train, y_train, X_test, features, attribute: str, vocab=None
) -> MitigationResult:
    """Pre-processing: strip each feature's linear correlation with the attribute.

    This method cannot see a missing value. ``CorrelationRemover`` raises on NaN,
    because it solves a linear projection that has no meaning over absent
    entries. For thin-file lending that is not a technicality: the missing
    bureau score *is* the defining fact about a new-to-credit applicant, and the
    booster elsewhere in this project consumes it natively.

    To give the method a fair hearing rather than disqualify it on a technical
    error, the bureau columns are median-imputed here and an explicit
    ``__missing__`` indicator is added for each, which is the standard remedy
    and preserves the fact of absence as a separate signal. The comparison
    records that this extra step was required, because it is a real cost: every
    deployment of this strategy must decide what to invent for the applicants
    who have no record.
    """
    from fairlearn.preprocessing import CorrelationRemover

    def with_attribute(frame: pd.DataFrame, medians=None):
        design = build_design_matrix(frame, features, vocab).copy()
        incomplete = [c for c in design.columns if design[c].isna().any()] if medians is None \
            else [c for c in medians]
        for column in incomplete:
            design[f"{column}__missing__"] = design[column].isna().astype(float)
        if medians is None:
            medians = {c: float(design[c].median()) for c in incomplete}
        for column, value in medians.items():
            design[column] = design[column].fillna(value)
        design["__protected__"] = pd.factorize(frame[attribute].astype(str))[0].astype(float)
        return design, medians

    train_design, medians = with_attribute(X_train)
    test_design, _ = with_attribute(X_test, medians)
    test_design = test_design[train_design.columns]

    remover = CorrelationRemover(sensitive_feature_ids=["__protected__"])
    train_clean = remover.fit_transform(train_design)
    test_clean = remover.transform(test_design)

    model = _booster().fit(train_clean, y_train)
    return MitigationResult(
        name="CorrelationRemover", family="pre-processing",
        scores=model.predict_proba(test_clean)[:, 1],
        needs_attribute_at_decision=True,
        note="Cannot accept NaN, so the missing bureau records had to be imputed before it "
             "would run. transform() also requires the sensitive column, so a deployed scorer "
             "must read the protected attribute for every application.",
    ).check_degeneracy()


def run_exponentiated_gradient(
    X_train, y_train, X_test, y_test, features, attribute: str, vocab=None
) -> MitigationResult:
    """In-processing: constrained optimisation under demographic parity."""
    from fairlearn.reductions import DemographicParity, ExponentiatedGradient

    train_design = build_design_matrix(X_train, features, vocab)
    test_design = build_design_matrix(X_test, features, vocab)

    reduction = ExponentiatedGradient(
        estimator=_booster(), constraints=DemographicParity(), eps=0.02, max_iter=25
    )
    reduction.fit(train_design, y_train, sensitive_features=X_train[attribute].astype(str))
    scores = _orient(np.asarray(reduction._pmf_predict(test_design))[:, 1], y_test)
    return MitigationResult(
        name="ExponentiatedGradient", family="in-processing", scores=scores,
        needs_attribute_at_decision=False,
        note="The attribute is used while fitting only; predict() takes features alone. "
             "On this problem it collapses to a trivial solution - see the diagnostic.",
    ).check_degeneracy()


def run_threshold_optimizer(
    X_train, y_train, X_test, y_test, features, attribute: str, vocab=None
) -> MitigationResult:
    """Post-processing: a separate decision threshold per group."""
    from fairlearn.postprocessing import ThresholdOptimizer

    train_design = build_design_matrix(X_train, features, vocab)
    test_design = build_design_matrix(X_test, features, vocab)

    optimizer = ThresholdOptimizer(
        estimator=_booster(), constraints="demographic_parity",
        objective="balanced_accuracy_score", prefit=False, predict_method="predict_proba",
    )
    optimizer.fit(train_design, y_train, sensitive_features=X_train[attribute].astype(str))
    pmf = optimizer._pmf_predict(test_design, sensitive_features=X_test[attribute].astype(str))
    scores = _orient(np.asarray(pmf)[:, 1], y_test)
    return MitigationResult(
        name="ThresholdOptimizer", family="post-processing", scores=scores,
        needs_attribute_at_decision=True,
        note="The per-group threshold is the mechanism: an applicant's group changes "
             "the bar they must clear, which is disparate treatment.",
    ).check_degeneracy()
