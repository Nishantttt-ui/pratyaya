"""Local embedding model.

Runs ``BAAI/bge-small-en-v1.5`` through ONNX Runtime on the CPU. This is a
deliberate choice over a hosted embeddings API:

* **No personal data leaves the machine.** Embedding happens in-process, which
  matters because the same component is used for applicant-facing text.
* **No per-query cost and no rate limit**, so the evaluation harness can run
  the full corpus repeatedly.
* **Deterministic.** The same text yields the same vector on every run, so a
  retrieval result recorded in an audit trail can be reproduced later.

The model is loaded lazily and cached, because construction downloads and
initialises the ONNX graph and takes a few seconds.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    from fastembed import TextEmbedding  # imported lazily: heavy import

    return TextEmbedding(model_name=model_name)


def embed_texts(texts: list[str], model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed documents, returning L2-normalised vectors.

    Normalising here means cosine similarity reduces to a dot product, both in
    NumPy and in pgvector.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)
    model = _load_model(model_name)
    vectors = np.vstack(list(model.embed(texts))).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


def embed_query(text: str, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a single query string."""
    return embed_texts([text], model_name=model_name)[0]
