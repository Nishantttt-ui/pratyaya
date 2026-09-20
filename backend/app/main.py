"""FastAPI application factory.

Startup cost is paid once. The model, the SHAP explainer and the embedded
policy corpus are loaded during the lifespan and held on ``app.state``; a
request never rebuilds them.

The vector store is chosen at startup: PostgreSQL with pgvector when a database
is configured and reachable, otherwise an in-memory store over the same corpus.
The fallback keeps the service runnable for a reviewer who has no database,
and the choice is reported on ``/health`` so it is never ambiguous which path
is live.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import pandas as pd
import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.app.api.v1.routers import assessments, auth, health
from backend.app.core.config import get_settings
from backend.app.llm.base import LLMError
from backend.app.llm.factory import build_provider
from backend.app.rag.corpus import load_corpus
from backend.app.rag.store import InMemoryVectorStore, PgVectorStore
from backend.app.repositories.users import seed_demo_users
from backend.app.services.decision_service import DecisionService
from ml.data.generator import GeneratorConfig, generate_population
from ml.explain.explainer import CreditExplainer

logger = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


def _configure_logging(level: str) -> None:
    """Structured JSON logs with secrets kept out by construction."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )


def _build_vector_store(settings):
    """Prefer pgvector; fall back to in-memory so the service still runs."""
    corpus = load_corpus(settings.policy_corpus_path)
    try:
        from sqlalchemy import create_engine

        engine = create_engine(
            settings.database_url.get_secret_value(), pool_pre_ping=True
        )
        store = PgVectorStore(engine)
        indexed = store.index(corpus)
        logger.info("vector_store_ready", kind="pgvector", chunks=indexed)
        return store, "pgvector", indexed
    except Exception as exc:  # noqa: BLE001 - any DB failure must not block startup
        logger.warning(
            "pgvector_unavailable_falling_back",
            error=f"{type(exc).__name__}: {str(exc)[:160]}",
        )
        store = InMemoryVectorStore()
        indexed = store.index(corpus)
        return store, "in_memory", indexed


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)

    explainer = CreditExplainer.from_artifacts(settings.model_path)
    app.state.model_ready = True

    store, kind, chunks = _build_vector_store(settings)
    app.state.vector_store_kind = kind
    app.state.corpus_size = chunks

    provider = None
    try:
        provider = build_provider(settings)
        app.state.provider_name = provider.name
        logger.info("llm_provider_ready", provider=provider.name, model=settings.llm_model)
    except (LLMError, ValueError) as exc:
        app.state.provider_name = None
        logger.warning(
            "llm_provider_unavailable",
            error=str(exc)[:200],
            effect="explanations will use the deterministic notice",
        )

    # Reference population: defines what recourse targets are attainable, and
    # backs the sample endpoint used by the interface.
    population: pd.DataFrame = generate_population(GeneratorConfig(n_applicants=5_000))
    app.state.population = population

    app.state.decision_service = DecisionService(
        explainer=explainer, store=store, provider=provider, population=population
    )

    users, generated = seed_demo_users(settings)
    app.state.users = users
    for username, password in generated.items():
        # Printed once, only for accounts whose password was not configured.
        logger.warning("generated_demo_credential", username=username, password=password)

    logger.info("startup_complete", vector_store=kind, corpus_chunks=chunks)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pratyaya — Explainable Credit Risk",
        description=(
            "Credit assessment for thin-file and new-to-credit applicants. "
            "The decision is made by a deterministic, auditable model; the "
            "language model only explains it."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Log the detail, return none of it.

        A stack trace or exception message in an HTTP response can disclose
        file paths, query fragments and configuration. The caller gets a
        correlation-free generic message; the detail stays in the logs.
        """
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=f"{type(exc).__name__}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    prefix = settings.api_v1_prefix
    app.include_router(health.router)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(assessments.router, prefix=prefix)
    return app


app = create_app()
