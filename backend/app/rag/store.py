"""Vector storage and retrieval over the regulatory corpus.

Two implementations sit behind one interface:

* ``PgVectorStore`` — PostgreSQL with the ``vector`` extension. This is the
  deployment target named in the brief, and the one used when a database is
  configured. Similarity search runs in the database, so retrieval scales with
  the corpus rather than with application memory, and the corpus is shared
  across API workers instead of being re-embedded per process.
* ``InMemoryVectorStore`` — exact NumPy cosine search over the same chunks.
  Used by the unit tests and as a local fallback. A 37-provision corpus fits
  comfortably in memory, so this returns identical results to the database
  path; it exists so that retrieval quality can be tested without standing up
  Postgres, not as a different algorithm.

Because ``embed_texts`` returns L2-normalised vectors, cosine similarity is a
plain dot product, and pgvector's ``<#>`` negative inner product operator gives
the same ordering.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np

from backend.app.rag.corpus import PolicyChunk
from backend.app.rag.embeddings import EMBEDDING_DIM, embed_query, embed_texts


@dataclass
class RetrievedChunk:
    """A corpus chunk together with how well it matched the query."""

    chunk: PolicyChunk
    score: float

    def to_citation(self) -> dict:
        return {
            "chunk_id": self.chunk.chunk_id,
            "heading": self.chunk.heading,
            "instrument": self.chunk.instrument,
            "citation": self.chunk.citation,
            "text": self.chunk.text,
            "score": round(self.score, 4),
        }


class VectorStore(abc.ABC):
    @abc.abstractmethod
    def index(self, chunks: list[PolicyChunk]) -> int:
        """Embed and store chunks. Returns the number indexed."""

    @abc.abstractmethod
    def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """Return the closest chunks to ``query``, best first."""


class InMemoryVectorStore(VectorStore):
    """Exact cosine search in NumPy."""

    def __init__(self) -> None:
        self._chunks: list[PolicyChunk] = []
        self._matrix: np.ndarray = np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    def index(self, chunks: list[PolicyChunk]) -> int:
        self._chunks = list(chunks)
        self._matrix = embed_texts([c.embedding_text() for c in self._chunks])
        return len(self._chunks)

    def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        if not self._chunks:
            return []
        scores = self._matrix @ embed_query(query)
        top = np.argsort(-scores)[:top_k]
        return [RetrievedChunk(self._chunks[i], float(scores[i])) for i in top]


class PgVectorStore(VectorStore):
    """PostgreSQL + pgvector backed store."""

    def __init__(self, engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        """Create the extension, table and index if they are absent."""
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS policy_chunk (
                        chunk_id     TEXT PRIMARY KEY,
                        heading      TEXT NOT NULL,
                        body         TEXT NOT NULL,
                        instrument   TEXT NOT NULL,
                        citation     TEXT NOT NULL,
                        authority    TEXT NOT NULL,
                        source_file  TEXT NOT NULL,
                        embedding    vector({EMBEDDING_DIM}) NOT NULL
                    )
                    """
                )
            )
            # Cosine distance index. Vectors are pre-normalised, so this is
            # equivalent to inner-product ordering.
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS policy_chunk_embedding_idx
                    ON policy_chunk USING hnsw (embedding vector_cosine_ops)
                    """
                )
            )

    def index(self, chunks: list[PolicyChunk]) -> int:
        from sqlalchemy import text

        self.ensure_schema()
        vectors = embed_texts([c.embedding_text() for c in chunks])
        rows = [
            {
                "chunk_id": chunk.chunk_id,
                "heading": chunk.heading,
                "body": chunk.text,
                "instrument": chunk.instrument,
                "citation": chunk.citation,
                "authority": chunk.authority,
                "source_file": chunk.source_file,
                "embedding": vector.tolist(),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO policy_chunk
                        (chunk_id, heading, body, instrument, citation,
                         authority, source_file, embedding)
                    VALUES
                        (:chunk_id, :heading, :body, :instrument, :citation,
                         :authority, :source_file, :embedding)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        heading = EXCLUDED.heading,
                        body = EXCLUDED.body,
                        instrument = EXCLUDED.instrument,
                        citation = EXCLUDED.citation,
                        authority = EXCLUDED.authority,
                        source_file = EXCLUDED.source_file,
                        embedding = EXCLUDED.embedding
                    """
                ),
                rows,
            )
        return len(rows)

    def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        from sqlalchemy import text

        vector = embed_query(query).tolist()
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT chunk_id, heading, body, instrument, citation,
                           authority, source_file,
                           1 - (embedding <=> CAST(:q AS vector)) AS score
                    FROM policy_chunk
                    ORDER BY embedding <=> CAST(:q AS vector)
                    LIMIT :k
                    """
                ),
                {"q": str(vector), "k": top_k},
            ).mappings().all()

        return [
            RetrievedChunk(
                PolicyChunk(
                    chunk_id=row["chunk_id"],
                    heading=row["heading"],
                    text=row["body"],
                    instrument=row["instrument"],
                    citation=row["citation"],
                    authority=row["authority"],
                    source_file=row["source_file"],
                ),
                float(row["score"]),
            )
            for row in result
        ]
