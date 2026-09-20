"""Evaluation harness.

Run with:  python eval/run_eval.py

Measures four things the system claims, and writes the numbers to
``eval/reports/evaluation.json`` so they can be quoted without being retyped.

1. **Retrieval quality** against a golden set of questions a borrower, an
   underwriter or an auditor would actually ask.
2. **Guardrail accuracy** as a classifier, on adversarial *and* benign cases.
   Benign cases carry equal weight: a guardrail that blocks legitimate
   explanations is a denial of service against the lender's own duty to give
   reasons, so precision matters as much as recall.
3. **Explanation faithfulness** - whether the reason codes actually decompose
   the model, measured as TreeSHAP additivity error across the population.
4. **Calibration** - whether a stated probability of default means what it
   says, measured as expected calibration error and the Brier score.

Everything here runs offline. None of it needs an LLM key or a database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import shap  # noqa: E402

from backend.app.llm.guardrails import check_prompt, verify_consistency  # noqa: E402
from backend.app.rag.corpus import load_corpus  # noqa: E402
from backend.app.rag.store import InMemoryVectorStore  # noqa: E402
from ml.data.generator import GeneratorConfig, generate_population  # noqa: E402
from ml.explain.explainer import CreditExplainer  # noqa: E402
from ml.training.features import build_design_matrix  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "eval" / "goldensets"
REPORTS = ROOT / "eval" / "reports"


def evaluate_retrieval() -> dict:
    cases = json.loads((GOLDEN / "retrieval_golden.json").read_text())["cases"]
    corpus = load_corpus(ROOT / "data" / "policy")
    store = InMemoryVectorStore()
    store.index(corpus)

    known = {c.chunk_id for c in corpus}
    unknown = {
        cid
        for case in cases
        for cid in [case["ideal"], *case["relevant"]]
        if cid not in known
    }
    if unknown:
        raise ValueError(
            f"golden set references provisions absent from the corpus: {sorted(unknown)}"
        )

    ideal_at_1 = relevant_at_1 = relevant_at_3 = relevant_at_5 = 0
    reciprocal_ranks: list[float] = []
    misses: list[dict] = []

    for case in cases:
        results = store.search(case["query"], top_k=5)
        ids = [r.chunk.chunk_id for r in results]
        relevant = set(case["relevant"])

        if ids and ids[0] == case["ideal"]:
            ideal_at_1 += 1
        if ids and ids[0] in relevant:
            relevant_at_1 += 1
        else:
            misses.append(
                {"query": case["query"], "expected": case["ideal"], "got": ids[:3]}
            )
        if relevant & set(ids[:3]):
            relevant_at_3 += 1
        if relevant & set(ids[:5]):
            relevant_at_5 += 1

        rank = next((i + 1 for i, cid in enumerate(ids) if cid in relevant), None)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    n = len(cases)
    return {
        "n_cases": n,
        "ideal_at_1": ideal_at_1 / n,
        "relevant_at_1": relevant_at_1 / n,
        "relevant_at_3": relevant_at_3 / n,
        "relevant_at_5": relevant_at_5 / n,
        "mrr": float(np.mean(reciprocal_ranks)),
        "misses_at_1": misses,
    }


def _classifier_scores(predictions: list[bool], truth: list[bool]) -> dict:
    tp = sum(p and t for p, t in zip(predictions, truth, strict=True))
    fp = sum(p and not t for p, t in zip(predictions, truth, strict=True))
    fn = sum((not p) and t for p, t in zip(predictions, truth, strict=True))
    tn = sum((not p) and (not t) for p, t in zip(predictions, truth, strict=True))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positives": tp, "false_positives": fp,
        "false_negatives": fn, "true_negatives": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "accuracy": (tp + tn) / len(truth),
    }


def evaluate_guardrails() -> dict:
    cases = json.loads((GOLDEN / "guardrail_cases.json").read_text())

    prompt_pred = [not check_prompt(c["text"]).passed for c in cases["prompt_cases"]]
    prompt_true = [c["should_block"] for c in cases["prompt_cases"]]

    output_pred = [
        not verify_consistency(c["text"], decision=c["decision"]).passed
        for c in cases["output_cases"]
    ]
    output_true = [c["should_block"] for c in cases["output_cases"]]

    failures = [
        {"kind": c["kind"], "text": c["text"][:70], "expected_block": t, "did_block": p}
        for c, p, t in zip(
            cases["prompt_cases"] + cases["output_cases"],
            prompt_pred + output_pred,
            prompt_true + output_true,
            strict=True,
        )
        if p != t
    ]

    return {
        "inbound": _classifier_scores(prompt_pred, prompt_true),
        "outbound": _classifier_scores(output_pred, output_true),
        "combined": _classifier_scores(prompt_pred + output_pred, prompt_true + output_true),
        "failures": failures,
    }


def evaluate_faithfulness(explainer: CreditExplainer, population) -> dict:
    """TreeSHAP additivity: do the reason codes actually decompose the model?"""
    sample = population.head(500)
    matrix = build_design_matrix(sample, explainer.features)
    booster = explainer._booster  # noqa: SLF001
    tree_explainer = shap.TreeExplainer(booster)
    values = np.asarray(tree_explainer.shap_values(matrix))
    base = float(np.ravel(tree_explainer.expected_value)[0])
    errors = np.abs((base + values.sum(axis=1)) - booster.decision_function(matrix))
    return {
        "n_applicants": int(len(sample)),
        "max_additivity_error": float(errors.max()),
        "mean_additivity_error": float(errors.mean()),
        "is_exact": bool(errors.max() < 1e-6),
    }


def evaluate_calibration(explainer: CreditExplainer, population, n_bins: int = 10) -> dict:
    """Expected calibration error: does a stated 8% risk mean 8 in 100?"""
    probabilities = explainer.predict_proba(population)
    outcomes = population["default_12m"].to_numpy()

    edges = np.quantile(probabilities, np.linspace(0, 1, n_bins + 1))
    edges[-1] += 1e-9
    ece = 0.0
    bins = []
    for i in range(n_bins):
        mask = (probabilities >= edges[i]) & (probabilities < edges[i + 1])
        if mask.sum() == 0:
            continue
        predicted = float(probabilities[mask].mean())
        observed = float(outcomes[mask].mean())
        weight = mask.sum() / len(probabilities)
        ece += weight * abs(predicted - observed)
        bins.append({
            "bin": i + 1, "n": int(mask.sum()),
            "predicted": round(predicted, 4), "observed": round(observed, 4),
        })

    brier = float(np.mean((probabilities - outcomes) ** 2))
    return {
        "expected_calibration_error": float(ece),
        "brier_score": brier,
        "base_rate": float(outcomes.mean()),
        "bins": bins,
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    explainer = CreditExplainer.from_artifacts(ROOT / "ml" / "artifacts" / "model.joblib")
    population = generate_population(GeneratorConfig(n_applicants=10_000))

    print("evaluating retrieval ...")
    retrieval = evaluate_retrieval()
    print("evaluating guardrails ...")
    guardrails = evaluate_guardrails()
    print("evaluating explanation faithfulness ...")
    faithfulness = evaluate_faithfulness(explainer, population)
    print("evaluating calibration ...")
    calibration = evaluate_calibration(explainer, population)

    report = {
        "retrieval": retrieval,
        "guardrails": guardrails,
        "faithfulness": faithfulness,
        "calibration": calibration,
    }
    (REPORTS / "evaluation.json").write_text(json.dumps(report, indent=2, default=float))

    print("\n" + "=" * 68)
    print("EVALUATION REPORT")
    print("=" * 68)
    print(f"\nRETRIEVAL  ({retrieval['n_cases']} golden queries)")
    print(f"  ideal provision at rank 1     {retrieval['ideal_at_1']:.1%}")
    print(f"  relevant provision at rank 1  {retrieval['relevant_at_1']:.1%}")
    print(f"  relevant provision in top 3   {retrieval['relevant_at_3']:.1%}")
    print(f"  relevant provision in top 5   {retrieval['relevant_at_5']:.1%}")
    print(f"  mean reciprocal rank          {retrieval['mrr']:.3f}")

    combined = guardrails["combined"]
    print(f"\nGUARDRAILS  ({len(guardrails['failures'])} misclassified)")
    print(f"  inbound  F1  {guardrails['inbound']['f1']:.3f}   "
          f"precision {guardrails['inbound']['precision']:.3f}  "
          f"recall {guardrails['inbound']['recall']:.3f}")
    print(f"  outbound F1  {guardrails['outbound']['f1']:.3f}   "
          f"precision {guardrails['outbound']['precision']:.3f}  "
          f"recall {guardrails['outbound']['recall']:.3f}")
    print(f"  combined F1  {combined['f1']:.3f}   accuracy {combined['accuracy']:.3f}")

    print(f"\nFAITHFULNESS  ({faithfulness['n_applicants']} applicants)")
    print(f"  max additivity error  {faithfulness['max_additivity_error']:.2e}")
    print(f"  exact decomposition   {faithfulness['is_exact']}")

    print("\nCALIBRATION")
    print(f"  expected calibration error  {calibration['expected_calibration_error']:.4f}")
    print(f"  Brier score                 {calibration['brier_score']:.4f}")
    print(f"  base rate                   {calibration['base_rate']:.4f}")

    if retrieval["misses_at_1"]:
        print(f"\nRETRIEVAL MISSES AT RANK 1 ({len(retrieval['misses_at_1'])})")
        for miss in retrieval["misses_at_1"]:
            print(f"  '{miss['query'][:52]}' expected {miss['expected']}, got {miss['got'][:2]}")
    if guardrails["failures"]:
        print("\nGUARDRAIL FAILURES")
        for failure in guardrails["failures"]:
            print(f"  [{failure['kind']}] expected_block={failure['expected_block']} "
                  f"got={failure['did_block']}  {failure['text'][:48]}")

    print("\nreport -> eval/reports/evaluation.json")


if __name__ == "__main__":
    main()
