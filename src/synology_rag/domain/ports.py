"""Ports: the interfaces the retrieval engine depends on.

Adapters (Qdrant, PostgreSQL, embedding providers) implement these protocols.
The engine is written against them and never imports a concrete adapter, which
keeps it unit-testable with in-memory fakes and free of write capabilities.

Internal transfer types (``VectorHit``, ``QueryFilter`` ...) are deliberately
minimal and read-only. ``QueryFilter`` is built by the engine from *validated*
inputs and mapped payload keys - clients can never supply a raw Qdrant filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class VectorHit:
    """A read result from the vector store."""

    id: str
    score: float
    payload: dict[str, Any]
    collection: str


@dataclass(slots=True)
class CollectionStats:
    """Collection info needed for startup checks and the collections endpoint."""

    name: str
    vector_dimensions: int | None
    distance: str | None
    points_count: int | None
    vector_names: list[str] = field(default_factory=list)
    # name -> vector size. Unnamed (single) vectors use the empty-string key.
    vector_sizes: dict[str, int] = field(default_factory=dict)

    def size_for(self, vector_name: str | None) -> int | None:
        """Vector size for a named vector, or the single/default vector."""
        if vector_name:
            return self.vector_sizes.get(vector_name)
        if "" in self.vector_sizes:
            return self.vector_sizes[""]
        if len(self.vector_sizes) == 1:
            return next(iter(self.vector_sizes.values()))
        return self.vector_dimensions


@dataclass(slots=True)
class MatchCondition:
    """`key` matches any of `values`. `key` is a trusted mapped payload key."""

    key: str
    values: list[Any]


@dataclass(slots=True)
class RangeCondition:
    """Inclusive range on a trusted mapped payload key."""

    key: str
    gte: float | int | datetime | None = None
    lte: float | int | datetime | None = None


@dataclass(slots=True)
class QueryFilter:
    """Engine-built filter. Only mapped payload keys ever appear here."""

    must_match: list[MatchCondition] = field(default_factory=list)
    must_range: list[RangeCondition] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.must_match and not self.must_range


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Generates query embeddings compatible with the existing index."""

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed_query(self, text: str) -> list[float]:
        """Return a single embedding vector for the query text."""

    async def health(self) -> bool:
        """Cheap, non-billable reachability/config check where possible."""


@runtime_checkable
class VectorRepository(Protocol):
    """Read-only access to the vector store. No write methods exist here."""

    async def search(
        self,
        *,
        collection: str,
        vector: list[float],
        vector_name: str | None,
        limit: int,
        query_filter: QueryFilter | None,
        score_threshold: float | None,
    ) -> list[VectorHit]: ...

    async def retrieve(
        self, *, collection: str, ids: list[str]
    ) -> list[VectorHit]: ...

    async def scroll(
        self,
        *,
        collection: str,
        scroll_filter: QueryFilter | None,
        limit: int,
    ) -> list[VectorHit]: ...

    async def collection_stats(self, collection: str) -> CollectionStats: ...

    async def collection_exists(self, collection: str) -> bool: ...


@runtime_checkable
class MetadataRepository(Protocol):
    """Read-only PostgreSQL metadata enrichment. SELECT only."""

    async def fetch_metadata(
        self, *, collection: str, document_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Return {document_id: {domain_field: value}} for the given documents."""

    async def health(self) -> bool: ...
