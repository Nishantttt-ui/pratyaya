"""Run this project's pipeline over real public credit datasets.

    python scripts/validate_on_real_data.py

The applicant population this project models is synthetic, and the obvious
objection is that its results could be an artefact of the generator. This script
answers that objection by running the *same* code - the one-hot design matrix,
histogram gradient boosting, isotonic calibration, exact TreeSHAP, and the
fairness audit - over two real datasets with genuinely observed defaults.

What it establishes, and what it does not:

* It establishes that the machinery is sound on real credit data: discrimination
  comparable to published results for these datasets, probabilities that
  calibrate, TreeSHAP that stays exact, and a fairness audit that produces
  sensible numbers against a real protected attribute.
* It does **not** transfer the inclusion finding. Neither dataset contains
  Account Aggregator-style alternative data, so the traditional-versus-inclusive
  comparison cannot be reproduced here. That claim rests on the synthetic
  population, and the README and deck both say so.

Results are written to ``eval/reports/real_benchmark.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import shap  # noqa: E402

from ml.data.real_benchmark import Benchmark, load_all  # noqa: E402
from ml.fairness.audit import audit_attribute  # noqa: E402
from ml.training.features import build_design_matrix  # noqa: E402
from ml.training.pipeline import (  # noqa: E402
    approval_threshold_for_rate,
    expected_calibration_error,
    train_model,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "eval" / "reports"
APPROVAL_RATE = 0.70


def evaluate(benchmark: Benchmark) -> dict:
    model, ev = train_model(
        benchmark.frame,
        features=benchmark.features,
        target=benchmark.target,
        vocab=benchmark.vocab or None,
    )
    p, y = ev["p_test"], ev["y_test"]
    test = benchmark.frame.iloc[ev["test_index"]].reset_index(drop=True)

    # TreeSHAP must stay exact on real data too, not only on ours.
    design = build_design_matrix(test.head(200), model.features, benchmark.vocab or None)
    explainer = shap.TreeExplainer(model.raw_estimator)
    values = np.asarray(explainer.shap_values(design))
    base = float(np.ravel(explainer.expected_value)[0])
    additivity = float(
        np.max(np.abs((base + values.sum(axis=1)) - model.raw_estimator.decision_function(design)))
    )

    threshold = approval_threshold_for_rate(p, APPROVAL_RATE)
    approved = p <= threshold

    fairness = {}
    for attribute in benchmark.protected:
        report = audit_attribute(
            protected=test[attribute], approved=approved, defaulted=y, attribute_name=attribute
        )
        fairness[attribute] = {
            "disparate_impact_ratio": report.disparate_impact_ratio,
            "passes_80_percent_rule": report.passes_80_percent_rule,
            "qualified_approval_gap": report.qualified_approval_gap,
            "groups": report.to_frame().to_dict(orient="records"),
        }

    return {
        "name": benchmark.name,
        "source": benchmark.source,
        "n_rows": int(len(benchmark.frame)),
        "n_features": len(model.features),
        "base_rate": benchmark.base_rate,
        "roc_auc": model.metrics["roc_auc"],
        "gini": model.metrics["gini"],
        "ks": model.metrics["ks"],
        "brier": model.metrics["brier"],
        "expected_calibration_error": expected_calibration_error(y, p),
        "shap_max_additivity_error": additivity,
        "shap_is_exact": bool(additivity < 1e-6),
        "approval_rate": float(approved.mean()),
        "bad_rate_among_approved": float(y[approved].mean()),
        "fairness": fairness,
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    results = []
    for benchmark in load_all():
        print(f"evaluating {benchmark.name} ({len(benchmark.frame):,} rows) ...")
        results.append(evaluate(benchmark))

    (REPORTS / "real_benchmark.json").write_text(json.dumps(results, indent=2, default=float))

    print("\n" + "=" * 76)
    print("PIPELINE VALIDATION ON REAL PUBLIC CREDIT DATA")
    print("=" * 76)
    for r in results:
        print(f"\n{r['name']}  —  {r['n_rows']:,} rows, {r['n_features']} features")
        print(f"  source                  {r['source']}")
        print(f"  base default rate       {r['base_rate']:.4f}")
        print(f"  ROC AUC                 {r['roc_auc']:.4f}     KS {r['ks']:.4f}")
        print(f"  Brier                   {r['brier']:.4f}     "
              f"ECE {r['expected_calibration_error']:.4f}")
        print(f"  TreeSHAP additivity     {r['shap_max_additivity_error']:.2e}  "
              f"({'exact' if r['shap_is_exact'] else 'NOT EXACT'})")
        print(f"  bad rate among approved {r['bad_rate_among_approved']:.4f} "
              f"at {r['approval_rate']:.0%} approval")
        for attribute, f in r["fairness"].items():
            verdict = "PASS" if f["passes_80_percent_rule"] else "FAIL"
            print(f"  fairness [{attribute}]  DI {f['disparate_impact_ratio']:.3f} ({verdict}), "
                  f"qualified gap {f['qualified_approval_gap']:.3f}")
            for g in f["groups"]:
                print(f"      {g['group']:<8} n={g['n']:<6} approved {g['approval_rate']:.3f}  "
                      f"qualified {g['qualified_approval_rate']:.3f}  "
                      f"bad-among-approved {g['default_rate_among_approved']:.3f}")
    print("\nreport -> eval/reports/real_benchmark.json")


if __name__ == "__main__":
    main()
