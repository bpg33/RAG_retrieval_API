"""Read-only Qdrant repository.

Only search, retrieve, scroll, and collection-info reads are implemented. There
is intentionally no upsert, delete, set-payload, or collection-management method
in this class: read-only is enforced by the absence of the capability.

Client-supplied values never reach Qdrant as raw filters. The engine passes a
typed :class:`QueryFilter` built from validated inputs and mapped payload keys,
which this adapter translates into a Qdrant ``Filter``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from synology_rag.config import Settings
from synology_rag.domain.errors import QdrantUnavailableError
from synology_rag.domain.ports import (
    CollectionStats,
    MatchCondition,
    QueryFilter,
    RangeCondition,
    VectorHit,
)

_TRANSIENT: tuple[type[Exception], ...] = (
    UnexpectedResponse,
    ResponseHandlingException,
    OSError,
    ConnectionError,
    TimeoutError,
)

# When prefer_grpc=true, transport failures surface as grpc.RpcError. Include it
# so they map to a retryable QdrantUnavailableError rather than a generic 500.
try:  # pragma: no cover - depends on optional grpc extra
    from grpc import RpcError as _GrpcRpcError  # type: ignore[import-untyped]

    _TRANSIENT = (*_TRANSIENT, _GrpcRpcError)
except ImportError:  # pragma: no cover
    pass


def _coerce_point_id(value: str) -> int | str:
    """Qdrant point ids are ints or UUID strings; preserve int ids."""
    if value.isdigit():
        return int(value)
    return value


def _match_condition(cond: MatchCondition) -> qm.FieldCondition:
    if len(cond.values) == 1:
        return qm.FieldCondition(key=cond.key, match=qm.MatchValue(value=cond.values[0]))
    return qm.FieldCondition(key=cond.key, match=qm.MatchAny(any=list(cond.values)))


def _range_condition(cond: RangeCondition) -> qm.FieldCondition:
    is_dt = isinstance(cond.gte, datetime) or isinstance(cond.lte, datetime)
    if is_dt:
        return qm.FieldCondition(
            key=cond.key,
            range=qm.DatetimeRange(gte=cond.gte, lte=cond.lte),
        )
    return qm.FieldCondition(
        key=cond.key,
        range=qm.Range(gte=cond.gte, lte=cond.lte),
    )


def _to_qdrant_filter(query_filter: QueryFilter | None) -> qm.Filter | None:
    if query_filter is None or query_filter.is_empty():
        return None
    must: list[qm.FieldCondition] = [_match_condition(m) for m in query_filter.must_match]
    must.extend(_range_condition(r) for r in query_filter.must_range)
    return qm.Filter(must=must)


class QdrantRepository:
    """Async, read-only access to approved Qdrant collections."""

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> QdrantRepository:
        client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=settings.qdrant_prefer_grpc,
            timeout=int(settings.qdrant_timeout_seconds),
        )
        return cls(client)

    async def search(
        self,
        *,
        collection: str,
        vector: list[float],
        vector_name: str | None,
        limit: int,
        query_filter: QueryFilter | None,
        score_threshold: float | None,
    ) -> list[VectorHit]:
        try:
            response = await self._client.query_points(
                collection_name=collection,
                query=vector,
                using=vector_name,
                limit=limit,
                query_filter=_to_qdrant_filter(query_filter),
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )
        except _TRANSIENT as exc:
            raise self._unavailable(exc) from exc
        return [
            VectorHit(
                id=str(p.id),
                score=float(p.score) if p.score is not None else 0.0,
                payload=dict(p.payload or {}),
                collection=collection,
            )
            for p in response.points
        ]

    async def retrieve(self, *, collection: str, ids: list[str]) -> list[VectorHit]:
        if not ids:
            return []
        try:
            records = await self._client.retrieve(
                collection_name=collection,
                ids=[_coerce_point_id(i) for i in ids],
                with_payload=True,
                with_vectors=False,
            )
        except _TRANSIENT as exc:
            raise self._unavailable(exc) from exc
        return [
            VectorHit(id=str(r.id), score=0.0, payload=dict(r.payload or {}), collection=collection)
            for r in records
        ]

    async def scroll(
        self,
        *,
        collection: str,
        scroll_filter: QueryFilter | None,
        limit: int,
    ) -> list[VectorHit]:
        try:
            records, _ = await self._client.scroll(
                collection_name=collection,
                scroll_filter=_to_qdrant_filter(scroll_filter),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except _TRANSIENT as exc:
            raise self._unavailable(exc) from exc
        return [
            VectorHit(id=str(r.id), score=0.0, payload=dict(r.payload or {}), collection=collection)
            for r in records
        ]

    async def collection_exists(self, collection: str) -> bool:
        try:
            return bool(await self._client.collection_exists(collection))
        except _TRANSIENT as exc:
            raise self._unavailable(exc) from exc

    async def collection_stats(self, collection: str) -> CollectionStats:
        try:
            info = await self._client.get_collection(collection)
        except _TRANSIENT as exc:
            raise self._unavailable(exc) from exc
        return _parse_collection_stats(collection, info)

    async def aclose(self) -> None:
        await self._client.close()

    @staticmethod
    def _unavailable(exc: Exception) -> QdrantUnavailableError:
        return QdrantUnavailableError(
            "The vector store is currently unavailable.",
            internal_detail=type(exc).__name__,
        )


def _parse_collection_stats(collection: str, info: Any) -> CollectionStats:
    """Extract vector sizes/distances from a Qdrant CollectionInfo."""
    vector_sizes: dict[str, int] = {}
    distance: str | None = None
    try:
        vectors = info.config.params.vectors
    except AttributeError:  # pragma: no cover - defensive
        vectors = None

    if isinstance(vectors, dict):
        for name, params in vectors.items():
            size = getattr(params, "size", None)
            if size is not None:
                vector_sizes[str(name)] = int(size)
            if distance is None:
                distance = _distance_str(getattr(params, "distance", None))
    elif vectors is not None:
        size = getattr(vectors, "size", None)
        if size is not None:
            vector_sizes[""] = int(size)
        distance = _distance_str(getattr(vectors, "distance", None))

    primary = vector_sizes.get("") or (next(iter(vector_sizes.values()), None))
    return CollectionStats(
        name=collection,
        vector_dimensions=primary,
        distance=distance,
        points_count=getattr(info, "points_count", None),
        vector_names=[n for n in vector_sizes if n],
        vector_sizes=vector_sizes,
    )


def _distance_str(distance: Any) -> str | None:
    if distance is None:
        return None
    return getattr(distance, "value", str(distance))
