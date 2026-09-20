"""Shared FastAPI dependencies.

Heavy objects - the model, the SHAP explainer, the embedded corpus - are built
once during application startup and held on ``app.state``. Rebuilding them per
request would add seconds of latency and re-download the embedding model.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.app.core.config import Settings, get_settings
from backend.app.repositories.users import UserRepository
from backend.app.services.decision_service import DecisionService


def get_decision_service(request: Request) -> DecisionService:
    return request.app.state.decision_service


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.users


SettingsDep = Annotated[Settings, Depends(get_settings)]
ServiceDep = Annotated[DecisionService, Depends(get_decision_service)]
UsersDep = Annotated[UserRepository, Depends(get_user_repository)]
