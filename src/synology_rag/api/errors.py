"""Exception handlers that map internal errors to safe JSON responses.

Never returns stack traces, SQL, secrets, internal paths, or full dependency
responses. Every response carries the request id and a stable error code.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from synology_rag.api.schemas import ErrorBody, ErrorResponseModel
from synology_rag.domain.errors import ErrorCode, RetrievalError
from synology_rag.observability.logging import get_logger
from synology_rag.observability.metrics import metrics

log = get_logger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _response(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponseModel(error=body).model_dump(),
        headers={"X-Request-ID": body.request_id or ""},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RetrievalError)
    async def _handle_retrieval_error(request: Request, exc: RetrievalError) -> JSONResponse:
        request_id = _request_id(request)
        metrics.increment("errors_total")
        metrics.increment(f"error.{exc.code.value}")
        log.warning(
            "request.error",
            code=exc.code.value,
            status=exc.http_status,
            request_id=request_id,
            internal_detail=exc.internal_detail,
        )
        return _response(
            exc.http_status,
            ErrorBody(
                code=exc.code.value,
                message=exc.message,
                retryable=exc.retryable,
                request_id=request_id,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _request_id(request)
        metrics.increment("errors_total")
        # Summarise which fields were invalid without echoing full payloads.
        fields = sorted({".".join(str(p) for p in e.get("loc", [])) for e in exc.errors()})
        return _response(
            422,
            ErrorBody(
                code=ErrorCode.INVALID_REQUEST.value,
                message=f"Invalid request. Problem fields: {', '.join(fields)}.",
                retryable=False,
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        metrics.increment("errors_total")
        # Log the type only; never leak the message/stack to the caller.
        log.error("request.unhandled", error_type=type(exc).__name__, request_id=request_id)
        return _response(
            500,
            ErrorBody(
                code=ErrorCode.INTERNAL_ERROR.value,
                message="An internal error occurred.",
                retryable=False,
                request_id=request_id,
            ),
        )
