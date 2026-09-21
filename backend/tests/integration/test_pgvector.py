"""pgvector retrieval, against a real database.

Skipped unless ``DATABASE_URL`` points at a reachable PostgreSQL with the
``vector`` extension, so the suite still runs on a machine with no database.
Marked ``integration`` for the same reason.

The assertion that matters is not that the SQL executes. It is that the
database path returns the *same* provisions in the *same* order as the
in-memory path. A silent divergence would mean the citations attached to a
credit decision depend on which backend happened to be available, which is not
a property a lender can defend.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def _database_url() -> str:
    """Read DATABASE_URL from the environment, falling back to the .env file.

    conftest sets a placeholder DATABASE_URL so the unit suite can construct
    Settings without a database, and that placeholder takes precedence over
    .env. This test needs the real one, so it reads the file directly. Parsing
    it by hand rather than sourcing it matters: a Neon URL contains an
    ampersand, which a shell would read as a background operator.
    """
    from pathlib import Path

    env_file = Path(__file__).resolve().parents[3] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DATABASE_URL", "")


def _engine_or_skip():
    url = _database_url()
    if not url or "localhost" in url or "unused" in url:
        pytest.skip("no external DATABASE_URL configured")
    from sqlalchemy import create_engine, text

    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as conn:
            available = conn.execute(
                text("select 1 from pg_available_extensions where name='vector'")
            ).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database unreachable: {type(exc).__name__}")
    if not available:
        pytest.skip("pgvector extension not available on this server")
    return engine


@pytest.fixture(scope="module")
def pg_store(corpus):
    from backend.app.rag.store import PgVectorStore

    store = PgVectorStore(_engine_or_skip())
    store.index(corpus)
    return store


def test_every_provision_is_indexed(pg_store, corpus):
    from sqlalchemy import text

    with pg_store._engine.connect() as conn:  # noqa: SLF001
        count = conn.execute(text("select count(*) from policy_chunk")).scalar()
        dims = conn.execute(text("select vector_dims(embedding) from policy_chunk limit 1")).scalar()
    assert count == len(corpus)
    assert dims == 384


def test_an_approximate_index_exists(pg_store):
    """Without an index, similarity search degrades to a sequential scan."""
    from sqlalchemy import text

    with pg_store._engine.connect() as conn:  # noqa: SLF001
        names = conn.execute(
            text("select indexdef from pg_indexes where tablename='policy_chunk'")
        ).scalars().all()
    assert any("hnsw" in d.lower() for d in names)


def test_reindex_is_idempotent(pg_store, corpus):
    """Re-running the indexer must upsert, not duplicate."""
    from sqlalchemy import text

    pg_store.index(corpus)
    with pg_store._engine.connect() as conn:  # noqa: SLF001
        assert conn.execute(text("select count(*) from policy_chunk")).scalar() == len(corpus)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("why was my loan application rejected", "FPC-01"),
        ("I have no credit history, is that held against me", "CIC-04"),
        ("can I withdraw permission to use my personal data", "DPDP-05"),
    ],
)
def test_retrieval_surfaces_the_governing_provision(pg_store, query, expected):
    assert expected in [r.chunk.chunk_id for r in pg_store.search(query, top_k=3)]


def test_database_and_memory_paths_agree(pg_store, vector_store):
    """The load-bearing test: both backends must rank identically."""
    queries = [
        "why was my loan application rejected",
        "can the lender use my UPI bank transaction data",
        "I have no credit history",
        "does the app need access to my contacts",
        "what charges must be disclosed before I sign",
    ]
    for query in queries:
        from_db = [r.chunk.chunk_id for r in pg_store.search(query, top_k=3)]
        from_memory = [r.chunk.chunk_id for r in vector_store.search(query, top_k=3)]
        assert from_db == from_memory, f"backends disagree on {query!r}"


def test_scores_are_ordered_and_bounded(pg_store):
    results = pg_store.search("consent for sharing financial data", top_k=5)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(-1.0 <= s <= 1.0 for s in scores)
