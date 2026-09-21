"""Measure what past policy hides, and how much of it can be recovered.

    python scripts/reject_inference_experiment.py

A credit model is trained on the applicants a previous policy approved, because
those are the only ones whose repayment was ever observed. The model is then
asked to rank *every* applicant, including the region its predecessor never lent
into. The training data is censored, and on a real book the size of the damage
is unknowable, since measuring it would require the very outcomes that are
missing.

The generated population knows them. So this simulates a prior policy, hides
exactly the outcomes that policy would have hidden, and compares three models on
the full applicant pool:

  oracle    trained on everyone, outcomes for rejects included. Unattainable in
            practice, and the only honest upper bound.
  naive     trained on the accepted book alone. What a lender actually does.
  corrected naive plus rejects re-entered under fuzzy augmentation.

The number that matters is the share of the oracle-to-naive gap that the
correction recovers. Results are written to
``eval/reports/reject_inference.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from ml.data.generator import (  # noqa: E402
    INCLUSIVE_FEATURES,
    TARGET_COLUMN,
    GeneratorConfig,
    generate_population,
)
from ml.fairness.audit import audit_attribute  # noqa: E402
from ml.training.features import build_design_matrix  # noqa: E402
from ml.training.pipeline import approval_threshold_for_rate, ks_statistic  # noqa: E402
from ml.training.reject_inference import (  # noqa: E402
    fit_naive,
    fit_oracle,
    fit_with_reject_inference,
    simulate_prior_policy,
)

ROOT = Path(__file__).resolve().parents[1]
FEATURES = INCLUSIVE_FEATURES
# A restricted, bureau-led view stands in for a legacy scorecard.
LEGACY_VIEW = ["bureau_score", "credit_history_months", "monthly_income_declared",
               "emi_to_income", "is_new_to_credit", "age"]
APPROVAL_RATE = 0.70


def score(model, frame, y, protected="gender") -> dict:
    p = model.predict_proba(build_design_matrix(frame, FEATURES))[:, 1]
    approved = p <= approval_threshold_for_rate(p, APPROVAL_RATE)
    audit = audit_attribute(
        protected=frame[protected], approved=approved, defaulted=y, attribute_name=protected
    )
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "ks": ks_statistic(y, p),
        "bad_rate_among_approved": float(y[approved].mean()),
        "qualified_approval_gap": audit.qualified_approval_gap,
    }


def main() -> None:
    frame = generate_population(GeneratorConfig(n_applicants=30_000))
    y_all = frame[TARGET_COLUMN].to_numpy().astype(int)

    train, test, y_train, y_test = train_test_split(
        frame, y_all, test_size=0.3, stratify=y_all, random_state=20260921
    )
    train = train.reset_index(drop=True)
    test = test.reset_index(drop=True)

    policy = simulate_prior_policy(
        train, LEGACY_VIEW, TARGET_COLUMN, approval_rate=0.6
    )
    accepted = train[policy.approved].reset_index(drop=True)
    rejected = train[~policy.approved].reset_index(drop=True)

    print("=" * 76)
    print("WHAT THE PREVIOUS POLICY HID")
    print("=" * 76)
    print(f"  applicants in training pool : {len(train):,}")
    print(f"  approved by prior policy    : {len(accepted):,} ({policy.approval_rate:.1%})")
    print(f"  rejected, outcome unobserved: {len(rejected):,}")
    print(f"  bad rate the book shows     : {policy.observed_bad_rate:.4f}")
    print(f"  bad rate of the whole pool  : {policy.true_bad_rate:.4f}")
    print(f"  understatement              : {policy.true_bad_rate - policy.observed_bad_rate:+.4f}")
    print("\n  A lender reading only their own book sees a portfolio that looks safer")
    print("  than the population they are actually underwriting.")

    print("\nfitting oracle, naive, and corrected models ...")
    oracle = fit_oracle(train, FEATURES, TARGET_COLUMN)
    naive = fit_naive(accepted, FEATURES, TARGET_COLUMN)

    results = {
        "oracle (sees rejects' outcomes)": score(oracle, test, y_test),
        "naive (accepted book only)": score(naive, test, y_test),
    }

    sweep = {}
    for multiplier in (1.0, 1.5, 2.0, 3.0):
        corrected = fit_with_reject_inference(
            accepted, rejected, FEATURES, TARGET_COLUMN, bad_rate_multiplier=multiplier
        )
        sweep[multiplier] = score(corrected, test, y_test)

    best_mult = max(sweep, key=lambda m: sweep[m]["roc_auc"])
    results[f"corrected (fuzzy augmentation, x{best_mult})"] = sweep[best_mult]

    print("\n" + "=" * 76)
    print("EVALUATED ON THE FULL APPLICANT POOL, NOT JUST THE ACCEPTED BOOK")
    print("=" * 76)
    print(pd.DataFrame(results).T.round(4).to_string())

    oracle_auc = results["oracle (sees rejects' outcomes)"]["roc_auc"]
    naive_auc = results["naive (accepted book only)"]["roc_auc"]
    best_auc = sweep[best_mult]["roc_auc"]
    gap = oracle_auc - naive_auc
    recovered = (best_auc - naive_auc) / gap if gap > 1e-9 else float("nan")

    print(f"\n  censoring cost      {gap:+.4f} AUC (oracle minus naive)")
    print(f"  correction recovered {best_auc - naive_auc:+.4f} AUC")
    print(f"  share of gap closed  {recovered:.1%}" if np.isfinite(recovered) else "")

    print("\n  BAD-RATE MULTIPLIER SWEEP (how much worse rejects are assumed to be)")
    for m, r in sweep.items():
        print(f"    x{m:<4} AUC {r['roc_auc']:.4f}   bad rate {r['bad_rate_among_approved']:.4f}")
    print("\n  The multiplier is a judgement, not a measurement. Sweeping it shows how")
    print("  sensitive the correction is to an assumption a lender has to make.")

    report = {
        "prior_policy": {
            "approval_rate": policy.approval_rate,
            "observed_bad_rate": policy.observed_bad_rate,
            "true_bad_rate": policy.true_bad_rate,
            "n_accepted": int(len(accepted)),
            "n_rejected": int(len(rejected)),
        },
        "results": results,
        "multiplier_sweep": {str(k): v for k, v in sweep.items()},
        "censoring_cost_auc": gap,
        "recovered_auc": best_auc - naive_auc,
        "share_of_gap_closed": None if not np.isfinite(recovered) else recovered,
        "best_multiplier": best_mult,
    }
    (ROOT / "eval" / "reports" / "reject_inference.json").write_text(
        json.dumps(report, indent=2, default=float)
    )
    print("\nreport -> eval/reports/reject_inference.json")


if __name__ == "__main__":
    main()
