"""REST request/response models and converters from domain objects.

These Pydantic models are the wire contract. The engine returns dataclasses;
these ``from_domain`` helpers translate them. Requests are strict
(``extra="forbid"``) so unknown fields are rejected rather than ignored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from synology_rag.domain.models import (
    Citation,
    CollectionInfo,
    DocumentMetadata,
    RetrievedChunk,
    SearchRequest,
    SearchResponse,
)

FilterValue = str | int | float | bool | list[Any]


class SearchRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1)
    collections: list[str] | None = None
    folders: list[str] | None = None
    file_types: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    minimum_score: float | None = None
    include_neighbours: bool = True
    neighbours_before: int | None = Field(default=None, ge=0)
    neighbours_after: int | None = Field(default=None, ge=0)
    metadata_filters: dict[str, FilterValue] | None = None

    def to_domain(self) -> SearchRequest:
        return SearchRequest(
            query=self.query,
            limit=self.limit,
            collections=self.collections,
            folders=self.folders,
            file_types=self.file_types,
            date_from=self.date_from,
            date_to=self.date_to,
            minimum_score=self.minimum_score,
            include_neighbours=self.include_neighbours,
            neighbours_before=self.neighbours_before,
            neighbours_after=self.neighbours_after,
            metadata_filters=self.metadata_filters,
        )


class ChunkModel(BaseModel):
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
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, chunk: RetrievedChunk) -> ChunkModel:
        return cls(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            text=chunk.text,
            score=chunk.score,
            rank=chunk.rank,
            collection=chunk.collection,
            filename=chunk.filename,
            title=chunk.title,
            page_number=chunk.page_number,
            slide_number=chunk.slide_number,
            sheet_name=chunk.sheet_name,
            section=chunk.section,
            file_type=chunk.file_type,
            source_uri=chunk.source_uri,
            modified_at=chunk.modified_at,
            is_neighbour=chunk.is_neighbour,
            parent_result_chunk_id=chunk.parent_result_chunk_id,
            truncated=chunk.truncated,
            metadata=chunk.metadata,
        )


class CitationModel(BaseModel):
    citation_id: str
    document_id: str
    chunk_ids: list[str]
    display_name: str
    locator: str | None = None
    source_uri: str | None = None
    modified_at: datetime | None = None

    @classmethod
    def from_domain(cls, citation: Citation) -> CitationModel:
        return cls(
            citation_id=citation.citation_id,
            document_id=citation.document_id,
            chunk_ids=citation.chunk_ids,
            display_name=citation.display_name,
            locator=citation.locator,
            source_uri=citation.source_uri,
            modified_at=citation.modified_at,
        )


class SearchResponseModel(BaseModel):
    query: str
    search_id: str
    elapsed_ms: int
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    results: list[ChunkModel] = Field(default_factory=list)
    citations: list[CitationModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, response: SearchResponse) -> SearchResponseModel:
        return cls(
            query=response.query,
            search_id=response.search_id,
            elapsed_ms=response.elapsed_ms,
            truncated=response.truncated,
            warnings=response.warnings,
            results=[ChunkModel.from_domain(c) for c in response.results],
            citations=[CitationModel.from_domain(c) for c in response.citations],
        )


class DocumentMetadataModel(BaseModel):
    document_id: str
    display_name: str
    title: str | None = None
    file_type: str | None = None
    source_uri: str | None = None
    modified_at: datetime | None = None
    created_at: datetime | None = None
    collection: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, doc: DocumentMetadata) -> DocumentMetadataModel:
        return cls(
            document_id=doc.document_id,
            display_name=doc.display_name,
            title=doc.title,
            file_type=doc.file_type,
            source_uri=doc.source_uri,
            modified_at=doc.modified_at,
            created_at=doc.created_at,
            collection=doc.collection,
            metadata=doc.metadata,
        )


class CollectionInfoModel(BaseModel):
    name: str
    description: str
    vector_dimensions: int | None = None
    distance: str | None = None
    points_count: int | None = None

    @classmethod
    def from_domain(cls, info: CollectionInfo) -> CollectionInfoModel:
        return cls(
            name=info.name,
            description=info.description,
            vector_dimensions=info.vector_dimensions,
            distance=info.distance,
            points_count=info.points_count,
        )


class CollectionsResponseModel(BaseModel):
    collections: list[CollectionInfoModel]


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None


class ErrorResponseModel(BaseModel):
    error: ErrorBody


class HealthModel(BaseModel):
    status: str


class ReadinessModel(BaseModel):
    status: str
    dependencies: dict[str, bool | None]
