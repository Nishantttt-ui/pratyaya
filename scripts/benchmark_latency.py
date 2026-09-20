"""Measure how long a decision actually takes.

    python scripts/benchmark_latency.py

A credit decision is made while an applicant waits, so the cost of
explainability is a real product constraint rather than a footnote. This
measures each stage separately, because the interesting question is not "is it
fast" but "what does each guarantee cost".

Reported as p50/p95/p99 rather than a mean: an average hides the tail, and the
tail is what an applicant experiences.

The language model is deliberately excluded. It is off the decision path, its
latency belongs to a third party, and including it would measure someone else's
network rather than this system.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.app.rag.corpus import load_corpus  # noqa: E402
from backend.app.rag.store import InMemoryVectorStore  # noqa: E402
from backend.app.services.notice import render_notice  # noqa: E402
from ml.data.generator import GeneratorConfig, generate_population  # noqa: E402
from ml.explain.explainer import CreditExplainer  # noqa: E402
from ml.explain.recourse import find_recourse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "eval" / "reports"
N = 120


def timed(fn, n: int = N) -> dict:
    samples = []
    for i in range(n):
        started = time.perf_counter()
        fn(i)
        samples.append((time.perf_counter() - started) * 1000)
    arr = np.array(samples)
    return {
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "n": n,
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    explainer = CreditExplainer.from_artifacts(ROOT / "ml" / "artifacts" / "model.joblib")
    population = generate_population(GeneratorConfig(n_applicants=4_000))
    store = InMemoryVectorStore()
    store.index(load_corpus(ROOT / "data" / "policy"))

    scores = explainer.predict_proba(population)
    declined = population[scores > explainer.threshold].reset_index(drop=True)
    rows = [population.iloc[[i]] for i in range(N)]
    declined_rows = [declined.iloc[[i % len(declined)]] for i in range(N)]

    print("warming caches ...")
    explainer.explain(rows[0])
    store.search("warm up the embedding model")

    stages = {
        "score_only": timed(lambda i: explainer.predict_proba(rows[i])),
        "score_and_reason_codes": timed(lambda i: explainer.explain(rows[i], top_n=4)),
        "recourse_search": timed(
            lambda i: find_recourse(declined_rows[i], explainer=explainer, population=population),
            n=40,
        ),
        "policy_retrieval": timed(
            lambda i: store.search("reasons for rejection of a loan", top_k=3)
        ),
        "render_notice": timed(lambda i: render_notice(explainer.explain(rows[i], top_n=4))),
    }

    (REPORTS / "latency.json").write_text(json.dumps(stages, indent=2))

    print("\n" + "=" * 68)
    print(f"DECISION LATENCY  (single applicant, {N} samples, CPU only)")
    print("=" * 68)
    print(f"{'stage':<26}{'p50':>10}{'p95':>10}{'p99':>10}")
    for name, s in stages.items():
        print(f"{name:<26}{s['p50_ms']:>9.2f}ms{s['p95_ms']:>9.2f}ms{s['p99_ms']:>9.2f}ms")
    print("\nThe language model is excluded: it is off the decision path and its")
    print("latency belongs to a third-party API, not to this system.")
    print("\nreport -> eval/reports/latency.json")


if __name__ == "__main__":
    main()
