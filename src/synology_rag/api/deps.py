"""FastAPI dependencies for accessing the shared container/service."""

from __future__ import annotations

from fastapi import Request

from synology_rag.container import AppContainer
from synology_rag.retrieval.service import RetrievalService


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[no-any-return]


def get_service(request: Request) -> RetrievalService:
    container: AppContainer = request.app.state.container
    return container.service
