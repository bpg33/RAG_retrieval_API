"""Typed domain objects returned by the retrieval engine.

These are plain dataclasses with no dependency on HTTP, MCP, Qdrant, or SQL
libraries, so the engine stays protocol-independent and unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SearchRequest:
    """A retrieval request in domain terms.

    Field names mirror the specification. The engine's validation stage clamps
    and normalises this into an internal, trusted request before use; clients
    never supply raw Qdrant filters or SQL.
    """

    query: str
    # None means "use the configured default"; the engine resolves and clamps.
    limit: int | None = None
    collections: list[str] | None = None
    folders: list[str] | None = None
    file_types: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    minimum_score: float | None = None
    include_neighbours: bool = True
    neighbours_before: int | None = None
    neighbours_after: int | None = None
    metadata_filters: dict[str, str | int | float | bool | list[Any]] | None = None


@dataclass(slots=True)
class RetrievedChunk:
    """A single passage returned from search or context expansion."""

    chunk_id: str
    document_id: str
    text: str
    score: float
    rank: int
    collection: str
    filename: str | None = None
    title: str | None = None
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    section: str | None = None
    file_type: str | None = None
    source_uri: str | None = None
    modified_at: datetime | None = None
    is_neighbour: bool = False
    parent_result_chunk_id: str | None = None
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Citation:
    """A stable, de-duplicated citation covering one or more chunks."""

    citation_id: str
    document_id: str
    chunk_ids: list[str]
    display_name: str
    locator: str | None = None
    source_uri: str | None = None
    modified_at: datetime | None = None


@dataclass(slots=True)
class SearchResponse:
    """The full result of a search: passages plus assembled citations."""

    query: str
    results: list[RetrievedChunk]
    citations: list[Citation]
    search_id: str
    elapsed_ms: int
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass(slots=True)
class DocumentMetadata:
    """Approved, client-safe metadata for a single document."""

    document_id: str
    display_name: str
    title: str | None = None
    file_type: str | None = None
    source_uri: str | None = None
    modified_at: datetime | None = None
    created_at: datetime | None = None
    collection: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CollectionInfo:
    """User-facing description of a searchable collection."""

    name: str
    description: str
    vector_dimensions: int | None = None
    distance: str | None = None
    points_count: int | None = None
