"""Shared fixtures.

The trained model and the embedded corpus are expensive to build, so they are
session-scoped. The population is generated per session from a fixed seed, which
keeps assertions about rates and distributions stable between runs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-only-secret-not-used-anywhere-else")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost:5432/unused")
os.environ.setdefault("DEMO_UNDERWRITER_PASSWORD", "test-underwriter-pw")
os.environ.setdefault("DEMO_APPLICANT_PASSWORD", "test-applicant-pw")
os.environ.setdefault("GEMINI_API_KEY", "")

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ml" / "artifacts" / "model.joblib"


@pytest.fixture(scope="session")
def population():
    from ml.data.generator import GeneratorConfig, generate_population

    return generate_population(GeneratorConfig(n_applicants=8_000))


@pytest.fixture(scope="session")
def fair_population():
    """A counterfactual population with both bias mechanisms switched off."""
    from ml.data.generator import GeneratorConfig, generate_population

    return generate_population(
        GeneratorConfig(n_applicants=8_000, availability_bias=0.0, income_declaration_bias=0.0)
    )


@pytest.fixture(scope="session")
def explainer():
    if not MODEL_PATH.exists():
        pytest.skip("model artifact absent; run `python scripts/train.py` first")
    from ml.explain.explainer import CreditExplainer

    return CreditExplainer.from_artifacts(MODEL_PATH)


@pytest.fixture(scope="session")
def corpus():
    from backend.app.rag.corpus import load_corpus

    return load_corpus(ROOT / "data" / "policy")


@pytest.fixture(scope="session")
def vector_store(corpus):
    from backend.app.rag.store import InMemoryVectorStore

    store = InMemoryVectorStore()
    store.index(corpus)
    return store
