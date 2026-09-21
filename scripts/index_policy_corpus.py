"""Index the regulatory corpus into PostgreSQL + pgvector, and verify it.

    python scripts/index_policy_corpus.py

Indexing is the easy half. The half that matters is the verification: the
pgvector path and the in-memory path must return the *same* provisions in the
*same* order for the same query. Retrieval that merely runs is not retrieval
that is correct, and a silent difference between the two would mean the
citations attached to a decision depend on which backend happened to be up.

The comparison uses the evaluation golden set, so it exercises the queries the
system is actually measured on.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

from sqlalchemy import create_engine, text  # noqa: E402

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.rag.corpus import load_corpus  # noqa: E402
from backend.app.rag.store import InMemoryVectorStore, PgVectorStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def redact(message: str) -> str:
    return re.sub(r"://[^@]+@", "://<redacted>@", message)


def main() -> None:
    settings = get_settings()
    corpus = load_corpus(ROOT / "data" / "policy")
    print(f"corpus: {len(corpus)} provisions")

    engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    store = PgVectorStore(engine)

    started = time.perf_counter()
    indexed = store.index(corpus)
    print(f"indexed {indexed} provisions into pgvector in {time.perf_counter() - started:.1f}s")

    with engine.connect() as conn:
        rows = conn.execute(text("select count(*) from policy_chunk")).scalar()
        dim = conn.execute(
            text("select vector_dims(embedding) from policy_chunk limit 1")
        ).scalar()
        idx = (
            conn.execute(
                text("select indexname from pg_indexes where tablename='policy_chunk'")
            )
            .scalars()
            .all()
        )
    print(f"rows in table: {rows} | embedding dims: {dim}")
    print(f"indexes: {', '.join(idx)}")

    # --- the verification that matters -------------------------------------
    memory = InMemoryVectorStore()
    memory.index(corpus)

    golden = ROOT / "eval" / "goldensets" / "retrieval_golden.json"
    cases = json.loads(golden.read_text())["cases"]
    agree = 0
    disagreements = []
    pg_times, mem_times = [], []

    for case in cases:
        query = case["query"]
        t0 = time.perf_counter()
        pg_hits = [r.chunk.chunk_id for r in store.search(query, top_k=3)]
        pg_times.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        mem_hits = [r.chunk.chunk_id for r in memory.search(query, top_k=3)]
        mem_times.append((time.perf_counter() - t0) * 1000)

        if pg_hits == mem_hits:
            agree += 1
        else:
            disagreements.append({"query": query, "pgvector": pg_hits, "in_memory": mem_hits})

    n = len(cases)
    print("\nAGREEMENT WITH THE IN-MEMORY PATH")
    print(f"  identical top-3, same order : {agree}/{n}")
    for d in disagreements:
        print(f"    '{d['query'][:48]}' pg={d['pgvector']} mem={d['in_memory']}")

    pg_times.sort()
    mem_times.sort()
    print("\nLATENCY PER QUERY (includes embedding the query locally)")
    pg50, pg95 = pg_times[len(pg_times) // 2], pg_times[int(len(pg_times) * 0.95)]
    m50, m95 = mem_times[len(mem_times) // 2], mem_times[int(len(mem_times) * 0.95)]
    print(f"  pgvector  p50 {pg50:6.1f} ms   p95 {pg95:6.1f} ms")
    print(f"  in-memory p50 {m50:6.1f} ms   p95 {m95:6.1f} ms")
    print("\n  The gap is the network round trip to the database region, not the search.")

    report = {
        "provisions_indexed": indexed,
        "embedding_dims": dim,
        "indexes": idx,
        "golden_queries": n,
        "identical_to_in_memory": agree,
        "disagreements": disagreements,
        "pgvector_p50_ms": round(pg50, 2),
        "in_memory_p50_ms": round(m50, 2),
    }
    (ROOT / "eval" / "reports" / "pgvector_verification.json").write_text(
        json.dumps(report, indent=2)
    )
    print("\nreport -> eval/reports/pgvector_verification.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never let a URL reach the console
        print(f"FAILED: {type(exc).__name__}: {redact(str(exc))[:400]}")
        raise SystemExit(1) from exc
