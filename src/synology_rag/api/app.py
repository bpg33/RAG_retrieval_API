"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from ulid import ULID

from synology_rag.api.errors import register_exception_handlers
from synology_rag.api.routes_documents import router as documents_router
from synology_rag.api.routes_health import router as health_router
from synology_rag.api.routes_search import router as search_router
from synology_rag.api.schemas import ErrorBody, ErrorResponseModel
from synology_rag.config import Settings
from synology_rag.container import AppContainer, build_container
from synology_rag.observability.logging import configure_logging, get_logger
from synology_rag.observability.metrics import metrics

log = get_logger(__name__)

_DESCRIPTION = """\
Read-only Retrieval-Augmented Generation over an existing Synology-hosted
Qdrant + PostgreSQL index. All endpoints are read-only; there are no write,
delete, indexing, SQL, or filesystem operations.
"""


def create_app(container: AppContainer | None = None) -> FastAPI:
    # Settings are needed at construction time for CORS and the body-size limit.
    # In production (uvicorn factory, no container) this loads from the
    # environment and fails closed on invalid configuration, same as the engine.
    settings = container.settings if container is not None else Settings()
    max_request_bytes = settings.max_request_bytes

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active = container or build_container()
        configure_logging(level=active.settings.log_level, json_logs=True)
        app.state.container = active
        _log_security_posture(active)
        await active.startup()
        try:
            yield
        finally:
            await active.shutdown()

    app = FastAPI(
        title="Synology RAG Retrieval API",
        version="0.1.0",
        description=_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "X-Client-Id"],
            allow_credentials=False,
        )

    @app.middleware("http")
    async def add_request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(ULID())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        oversized = _reject_if_oversized(request, request_id, max_request_bytes)
        if oversized is not None:
            structlog.contextvars.clear_contextvars()
            return oversized

        start = perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        elapsed_ms = (perf_counter() - start) * 1000
        metrics.observe_ms("http_request", elapsed_ms)
        response.headers["X-Request-ID"] = request_id
        return response

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(documents_router)

    @app.get("/metrics", tags=["ops"])
    async def get_metrics() -> dict[str, object]:
        """Local operational counters and latencies (no secrets, no content)."""
        return metrics.snapshot()

    return app


def _reject_if_oversized(
    request: Request, request_id: str, max_bytes: int
) -> JSONResponse | None:
    """Return a 413 response if the declared body exceeds the configured limit."""
    content_length = request.headers.get("content-length")
    if content_length is None:
        return None
    try:
        declared = int(content_length)
    except ValueError:
        return None
    if declared <= max_bytes:
        return None
    metrics.increment("errors_total")
    body = ErrorResponseModel(
        error=ErrorBody(
            code="invalid_request",
            message=f"Request body exceeds the maximum of {max_bytes} bytes.",
            retryable=False,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=413, content=body.model_dump(), headers={"X-Request-ID": request_id}
    )


def _log_security_posture(container: AppContainer) -> None:
    settings = container.settings
    if not settings.local_api_key:
        log.warning(
            "security.auth_disabled",
            detail="LOCAL_API_KEY is unset; the REST API is unauthenticated.",
        )
    if not settings.bind_is_local:
        log.warning("security.non_local_bind", bind_host=settings.bind_host)
    if settings.log_content:
        log.warning(
            "security.content_logging_enabled",
            detail="LOG_CONTENT=true logs query and passage text. Development only.",
        )
