"""Compare algorithmic bias mitigation against widening the evidence.

    python scripts/compare_mitigations.py

This project argues that the disparity in thin-file lending lives in the
evidence rather than the algorithm. That argument is only honest if the standard
algorithmic remedies were actually tried, so this script runs three of them
against the same data, the same split and the same approval rate, and reports
what each costs.

It also records something the accuracy and fairness columns do not capture:
whether a strategy needs to read the applicant's protected attribute **at
decision time**. In lending that is not a footnote. A remedy that applies a
different rule depending on an applicant's gender is disparate treatment, not a
cure for it.

Results are written to ``eval/reports/mitigation_comparison.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from ml.data.generator import (  # noqa: E402
    INCLUSIVE_FEATURES,
    TARGET_COLUMN,
    TRADITIONAL_FEATURES,
    GeneratorConfig,
    generate_population,
)
from ml.fairness.audit import audit_attribute  # noqa: E402
from ml.fairness.mitigation import (  # noqa: E402
    run_baseline,
    run_correlation_remover,
    run_exponentiated_gradient,
    run_threshold_optimizer,
)
from ml.training.pipeline import approval_threshold_for_rate, ks_statistic  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "eval" / "reports"
ATTRIBUTE = "gender"
APPROVAL_RATE = 0.70
N = 18_000


def score_strategy(result, X_test, y_test) -> dict:
    """Evaluate one strategy at the common approval rate."""
    threshold = approval_threshold_for_rate(result.scores, APPROVAL_RATE)
    approved = result.scores <= threshold
    audit = audit_attribute(
        protected=X_test[ATTRIBUTE], approved=approved, defaulted=y_test, attribute_name=ATTRIBUTE
    )
    groups = {g.group: g for g in audit.groups}
    return {
        "strategy": result.name,
        "family": result.family,
        "needs_attribute_at_decision": result.needs_attribute_at_decision,
        "note": result.note,
        "degenerate": result.degenerate,
        "diagnostic": result.diagnostic,
        # Quoted as None for a degenerate strategy: an AUC would imply a ranking
        # it does not produce.
        "roc_auc": None if result.degenerate else float(roc_auc_score(y_test, result.scores)),
        "ks": None if result.degenerate else ks_statistic(y_test, result.scores),
        "approval_rate": float(approved.mean()),
        "bad_rate_among_approved": float(y_test[approved].mean()),
        "disparate_impact_ratio": audit.disparate_impact_ratio,
        "qualified_approval_gap": audit.qualified_approval_gap,
        "female_qualified_approval": groups["female"].qualified_approval_rate,
        "male_qualified_approval": groups["male"].qualified_approval_rate,
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    frame = generate_population(GeneratorConfig(n_applicants=N))
    y = frame[TARGET_COLUMN].to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        frame, y, test_size=0.25, stratify=y, random_state=20260921
    )
    print(f"population {N:,} | train {len(X_train):,} | test {len(X_test):,}\n")

    runs = []
    trad, incl = TRADITIONAL_FEATURES, INCLUSIVE_FEATURES
    steps = [
        ("Baseline (bureau only)",
         lambda: run_baseline(X_train, y_train, X_test, trad)),
        ("Alternative data (this project)",
         lambda: run_baseline(X_train, y_train, X_test, incl)),
        ("CorrelationRemover",
         lambda: run_correlation_remover(X_train, y_train, X_test, trad, ATTRIBUTE)),
        ("ExponentiatedGradient",
         lambda: run_exponentiated_gradient(
             X_train, y_train, X_test, y_test, trad, ATTRIBUTE)),
        ("ThresholdOptimizer",
         lambda: run_threshold_optimizer(
             X_train, y_train, X_test, y_test, trad, ATTRIBUTE)),
    ]

    for label, fn in steps:
        started = time.perf_counter()
        print(f"  running {label} ...", flush=True)
        result = fn()
        if label == "Alternative data (this project)":
            result.name = "Alternative data"
            result.family = "wider evidence"
            result.note = ("No mitigation algorithm. The protected attribute is read at "
                           "neither training nor decision time.")
        row = score_strategy(result, X_test, y_test)
        row["seconds"] = round(time.perf_counter() - started, 1)
        runs.append(row)

    (REPORTS / "mitigation_comparison.json").write_text(
        json.dumps({"approval_rate": APPROVAL_RATE, "n": N, "attribute": ATTRIBUTE, "runs": runs},
                   indent=2, default=float)
    )

    table = pd.DataFrame([{
        "strategy": r["strategy"],
        "family": r["family"],
        "AUC": "n/a" if r["degenerate"] else round(r["roc_auc"], 4),
        "bad_rate": round(r["bad_rate_among_approved"], 4),
        "DI": round(r["disparate_impact_ratio"], 3),
        "qual_gap": round(r["qualified_approval_gap"], 4),
        "needs_attr": "YES" if r["needs_attribute_at_decision"] else "no",
        "usable": "no" if r["degenerate"] else "yes",
    } for r in runs])

    print("\n" + "=" * 96)
    print(f"BIAS MITIGATION COMPARED  (approval rate fixed at {APPROVAL_RATE:.0%}, "
          f"attribute = {ATTRIBUTE})")
    print("=" * 96)
    print(table.to_string(index=False))
    print("\n'needs_attr' = the strategy must read the applicant's protected "
          "attribute at DECISION time.")
    print("'usable'     = emits a score that can be thresholded at a chosen approval rate.")
    for r in runs:
        if r["degenerate"]:
            print(f"\n  {r['strategy']}: {r['diagnostic']}")
    print("\nreport -> eval/reports/mitigation_comparison.json")


if __name__ == "__main__":
    main()
