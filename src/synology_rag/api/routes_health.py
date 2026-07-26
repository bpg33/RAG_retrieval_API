"""Health and readiness endpoints (unauthenticated, outside /api/v1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from synology_rag.api.deps import get_service
from synology_rag.api.schemas import HealthModel, ReadinessModel
from synology_rag.retrieval.service import RetrievalService

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthModel)
async def live() -> HealthModel:
    """Liveness: confirms the process is running. Does not query dependencies."""
    return HealthModel(status="alive")


@router.get("/health/ready", response_model=ReadinessModel)
async def ready(
    response: Response, service: RetrievalService = Depends(get_service)
) -> ReadinessModel:
    """Readiness: checks required dependencies with short timeouts."""
    deps = await service.readiness()
    ok = deps.get("qdrant") is True and deps.get("embedding") is True
    if deps.get("postgres") is False:
        ok = False
    if not ok:
        response.status_code = 503
    return ReadinessModel(status="ready" if ok else "not_ready", dependencies=deps)
