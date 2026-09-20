"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    """Report component readiness.

    Deliberately unauthenticated and free of configuration detail: it reports
    whether each component loaded, never which provider key is set or where the
    database lives.
    """
    state = request.app.state
    return {
        "status": "ok",
        "components": {
            "model": getattr(state, "model_ready", False),
            "policy_corpus": getattr(state, "corpus_size", 0),
            "vector_store": getattr(state, "vector_store_kind", "none"),
            "llm_provider": getattr(state, "provider_name", None) or "not_configured",
        },
    }
