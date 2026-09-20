"""Fairness audit correctness.

An audit that cannot be trusted is worse than none, so these tests check both
directions: that it detects disparity when disparity exists, and that it stays
quiet when it does not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.fairness.audit import DISPARATE_IMPACT_THRESHOLD, audit_all, audit_attribute


def _frame(groups):
    return pd.DataFrame({"gender": groups})


def test_equal_treatment_yields_a_ratio_of_one():
    protected = pd.Series(["female"] * 100 + ["male"] * 100)
    approved = np.array([True] * 50 + [False] * 50 + [True] * 50 + [False] * 50)
    defaulted = np.zeros(200, dtype=int)
    report = audit_attribute(
        protected=protected, approved=approved, defaulted=defaulted, attribute_name="gender"
    )
    assert report.disparate_impact_ratio == pytest.approx(1.0)
    assert report.passes_80_percent_rule


def test_severe_disparity_fails_the_eighty_percent_rule():
    protected = pd.Series(["female"] * 100 + ["male"] * 100)
    # 30% of women approved, 90% of men: ratio 0.333
    approved = np.array([True] * 30 + [False] * 70 + [True] * 90 + [False] * 10)
    defaulted = np.zeros(200, dtype=int)
    report = audit_attribute(
        protected=protected, approved=approved, defaulted=defaulted, attribute_name="gender"
    )
    assert report.disparate_impact_ratio == pytest.approx(1 / 3, abs=0.01)
    assert not report.passes_80_percent_rule


def test_threshold_boundary_is_inclusive():
    protected = pd.Series(["female"] * 100 + ["male"] * 100)
    approved = np.array([True] * 80 + [False] * 20 + [True] * 100)
    defaulted = np.zeros(200, dtype=int)
    report = audit_attribute(
        protected=protected, approved=approved, defaulted=defaulted, attribute_name="gender"
    )
    assert report.disparate_impact_ratio == pytest.approx(DISPARATE_IMPACT_THRESHOLD)
    assert report.passes_80_percent_rule


def test_qualified_approval_rate_considers_only_those_who_would_repay():
    """The metric must ignore applicants who would have defaulted."""
    protected = pd.Series(["female"] * 4 + ["male"] * 4)
    #                      good  good  bad   bad  | good  good  bad   bad
    approved = np.array([True, False, True, True, True, True, False, False])
    defaulted = np.array([0, 0, 1, 1, 0, 0, 1, 1])
    report = audit_attribute(
        protected=protected, approved=approved, defaulted=defaulted, attribute_name="gender"
    )
    rates = {g.group: g.qualified_approval_rate for g in report.groups}
    assert rates["female"] == pytest.approx(0.5)   # 1 of 2 good women approved
    assert rates["male"] == pytest.approx(1.0)     # 2 of 2 good men approved
    assert report.qualified_approval_gap == pytest.approx(0.5)


def test_audit_reports_group_sizes():
    protected = pd.Series(["female"] * 30 + ["male"] * 70)
    approved = np.ones(100, dtype=bool)
    defaulted = np.zeros(100, dtype=int)
    report = audit_attribute(
        protected=protected, approved=approved, defaulted=defaulted, attribute_name="gender"
    )
    assert {g.group: g.n for g in report.groups} == {"female": 30, "male": 70}


def test_audit_all_covers_every_requested_attribute(population):
    approved = np.random.default_rng(0).random(len(population)) < 0.7
    reports = audit_all(
        population,
        approved=approved,
        defaulted=population["default_12m"].to_numpy(),
        attributes=["gender", "region_tier"],
    )
    assert set(reports) == {"gender", "region_tier"}
    assert reports["gender"].to_frame().shape[0] == 2
