"""MCP tool implementations.

Pure functions over a :class:`RetrievalService`, kept separate from the FastMCP
wiring so they can be unit/contract tested directly. Every tool validates its
inputs through the engine and returns bounded, structured results. Domain errors
are returned as structured ``error`` payloads so the client model gets a clear,
safe message instead of a transport-level failure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from synology_rag.domain.errors import InvalidRequestError, RetrievalError
from synology_rag.domain.models import SearchRequest
from synology_rag.mcp.schemas import (
    format_collections,
    format_document,
    format_error,
    format_search_response,
)
from synology_rag.observability import audit
from synology_rag.retrieval.service import RetrievalService


def _parse_dt(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InvalidRequestError(f"{field} must be an ISO-8601 date-time.") from exc


async def search_documents(
    service: RetrievalService,
    *,
    query: str,
    limit: int | None = None,
    collections: list[str] | None = None,
    folders: list[str] | None = None,
    file_types: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_neighbours: bool = True,
) -> dict[str, Any]:
    try:
        request = SearchRequest(
            query=query,
            limit=limit,
            collections=collections,
            folders=folders,
            file_types=file_types,
            date_from=_parse_dt(date_from, "date_from"),
            date_to=_parse_dt(date_to, "date_to"),
            include_neighbours=include_neighbours,
        )
        response = await service.search(request)
    except RetrievalError as exc:
        return format_error(exc.code.value, exc.message, exc.retryable)

    audit.record_search(
        client="mcp",
        search_id=response.search_id,
        collections=collections or [],
        document_ids=[c.document_id for c in response.results],
        result_count=len(response.results),
        success=True,
    )
    return format_search_response(response)


async def get_document_metadata(
    service: RetrievalService, *, document_id: str
) -> dict[str, Any]:
    try:
        doc = await service.get_document_metadata(document_id)
    except RetrievalError as exc:
        return format_error(exc.code.value, exc.message, exc.retryable)
    return format_document(doc)


async def get_chunk_context(
    service: RetrievalService,
    *,
    chunk_id: str,
    neighbours_before: int = 1,
    neighbours_after: int = 1,
) -> dict[str, Any]:
    try:
        response = await service.get_chunk_context(
            chunk_id,
            neighbours_before=neighbours_before,
            neighbours_after=neighbours_after,
        )
    except RetrievalError as exc:
        return format_error(exc.code.value, exc.message, exc.retryable)
    return format_search_response(response)


async def list_document_collections(service: RetrievalService) -> dict[str, Any]:
    infos = await service.list_collections()
    return format_collections(infos)
