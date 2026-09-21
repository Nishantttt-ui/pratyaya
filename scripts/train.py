"""Train, evaluate, audit and persist the credit decisioning model.

Run with:  python scripts/train.py

Produces, under ``ml/artifacts/``:
  model.joblib          the calibrated model plus its feature contract
  metrics.json          held-out performance and fairness results
  shap_background.csv   reference sample used by the explainability layer

and a human-readable comparison under ``eval/reports/``.

The script trains **two** models on identical splits: one restricted to the
traditional bureau record, one that also sees consented alternative data. The
comparison between them is the central empirical claim of this project, so it is
regenerated here rather than quoted from a notebook.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python scripts/train.py` to work without the package being installed
# and without the caller having to set PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import pandas as pd

from ml.data.generator import (
    INCLUSIVE_FEATURES,
    TARGET_COLUMN,
    PROTECTED_ATTRIBUTES,
    TRADITIONAL_FEATURES,
    GeneratorConfig,
    generate_population,
)
from ml.fairness.audit import audit_all
from ml.training.pipeline import approval_threshold_for_rate, prepare_frame, train_model

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "ml" / "artifacts"
REPORTS = ROOT / "eval" / "reports"
DATA = ROOT / "data" / "processed"

APPROVAL_RATE = 0.70
SHAP_BACKGROUND_N = 200


def _evaluate(df: pd.DataFrame, features: list[str], label: str) -> dict:
    model, ev = train_model(df, features=features)
    test = df.iloc[ev["test_index"]].reset_index(drop=True)
    p, y = ev["p_test"], ev["y_test"]
    threshold = approval_threshold_for_rate(p, APPROVAL_RATE)
    approved = p <= threshold

    reports = audit_all(test, approved=approved, defaulted=y, attributes=PROTECTED_ATTRIBUTES)
    ntc = test["is_new_to_credit"].to_numpy().astype(bool)
    creditworthy = y == 0

    summary = {
        "label": label,
        "n_features": len(model.features),
        **{k: v for k, v in model.metrics.items()},
        "approval_threshold": threshold,
        "approval_rate": float(approved.mean()),
        "bad_rate_among_approved": float(y[approved].mean()),
        "ntc_approval_rate": float(approved[ntc].mean()),
        "creditworthy_ntc_approval_rate": float(approved[ntc & creditworthy].mean()),
        "fairness": {
            name: {
                "disparate_impact_ratio": rep.disparate_impact_ratio,
                "passes_80_percent_rule": rep.passes_80_percent_rule,
                "qualified_approval_gap": rep.qualified_approval_gap,
                "groups": rep.to_frame().to_dict(orient="records"),
            }
            for name, rep in reports.items()
        },
    }
    return {"model": model, "eval": ev, "summary": summary, "threshold": threshold}


def _deltas(traditional: dict, inclusive: dict) -> dict:
    """Inclusive minus traditional, for each headline measure."""
    trad_gender = traditional["fairness"]["gender"]
    incl_gender = inclusive["fairness"]["gender"]
    return {
        "roc_auc": inclusive["roc_auc"] - traditional["roc_auc"],
        "bad_rate_among_approved": (
            inclusive["bad_rate_among_approved"] - traditional["bad_rate_among_approved"]
        ),
        "creditworthy_ntc_approval_rate": (
            inclusive["creditworthy_ntc_approval_rate"]
            - traditional["creditworthy_ntc_approval_rate"]
        ),
        "disparate_impact_gender": (
            incl_gender["disparate_impact_ratio"] - trad_gender["disparate_impact_ratio"]
        ),
        "qualified_approval_gap_gender": (
            incl_gender["qualified_approval_gap"] - trad_gender["qualified_approval_gap"]
        ),
    }


def main() -> None:
    for directory in (ARTIFACTS, REPORTS, DATA):
        directory.mkdir(parents=True, exist_ok=True)

    print("generating population ...")
    df = generate_population(GeneratorConfig(n_applicants=30_000))
    df.to_csv(DATA / "applications.csv", index=False)
    print(f"  {len(df):,} applicants -> data/processed/applications.csv")

    # A small, committed slice so the repository shows what the data looks like
    # without anyone having to run training first. The full file is a build
    # output and stays git-ignored; this one is stratified over the
    # characteristics that matter to the argument, so it is representative
    # rather than just the first few hundred rows.
    # Built by concatenating per-stratum samples rather than groupby.apply:
    # pandas 3 excludes the grouping columns from the applied frame, which
    # silently dropped gender, is_new_to_credit and the outcome - the three
    # columns that make this sample worth looking at.
    strata = [
        group.sample(min(len(group), 40), random_state=7)
        for _, group in df.groupby(
            ["gender", "is_new_to_credit", TARGET_COLUMN], observed=True
        )
    ]
    sample = pd.concat(strata).sort_values("applicant_id")
    sample.to_csv(ROOT / "data" / "sample_applications.csv", index=False)
    print(f"  {len(sample)} row sample -> data/sample_applications.csv (committed)")

    print("\ntraining TRADITIONAL (bureau only) ...")
    traditional = _evaluate(df, TRADITIONAL_FEATURES, "traditional_bureau_only")
    print(f"  AUC {traditional['summary']['roc_auc']:.4f}  KS {traditional['summary']['ks']:.4f}")

    print("training INCLUSIVE (+ alternative data) ...")
    inclusive = _evaluate(df, INCLUSIVE_FEATURES, "inclusive_alternative_data")
    print(f"  AUC {inclusive['summary']['roc_auc']:.4f}  KS {inclusive['summary']['ks']:.4f}")

    # The inclusive model is the one that goes into production.
    model = inclusive["model"]
    joblib.dump(
        {
            "estimator": model.estimator,
            "raw_estimator": model.raw_estimator,
            "features": model.features,
            "design_columns": model.design_columns,
            "categorical_columns": model.categorical_columns,
            "metrics": model.metrics,
            "approval_threshold": inclusive["threshold"],
            "approval_rate": APPROVAL_RATE,
        },
        ARTIFACTS / "model.joblib",
    )

    # A fixed reference sample so SHAP explanations are reproducible between runs.
    background = prepare_frame(df.sample(SHAP_BACKGROUND_N, random_state=7), model.features)
    background.to_csv(ARTIFACTS / "shap_background.csv", index=False)

    results = {
        "approval_rate_held_at": APPROVAL_RATE,
        "traditional": traditional["summary"],
        "inclusive": inclusive["summary"],
        "deltas": _deltas(traditional["summary"], inclusive["summary"]),
    }
    (ARTIFACTS / "metrics.json").write_text(json.dumps(results, indent=2, default=float))
    (REPORTS / "inclusion_experiment.json").write_text(json.dumps(results, indent=2, default=float))

    print("\n" + "=" * 78)
    print("INCLUSION EXPERIMENT (approval rate held constant at %.0f%%)" % (APPROVAL_RATE * 100))
    print("=" * 78)
    rows = []
    for key in ("traditional", "inclusive"):
        s = results[key]
        rows.append(
            {
                "model": s["label"],
                "auc": round(s["roc_auc"], 4),
                "ks": round(s["ks"], 4),
                "bad_rate_approved": round(s["bad_rate_among_approved"], 4),
                "creditworthy_ntc_approved": round(s["creditworthy_ntc_approval_rate"], 4),
                "di_gender": round(s["fairness"]["gender"]["disparate_impact_ratio"], 4),
                "qual_gap_gender": round(s["fairness"]["gender"]["qualified_approval_gap"], 4),
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nartifacts -> ml/artifacts/{model.joblib,metrics.json,shap_background.csv}")


if __name__ == "__main__":
    main()
