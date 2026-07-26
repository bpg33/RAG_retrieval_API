"""In-memory fakes implementing the domain ports for fast, deterministic tests.

These let the full retrieval pipeline run without Qdrant, PostgreSQL, or a live
embedding service. They implement only read operations - matching the read-only
production adapters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from synology_rag.domain.ports import (
    CollectionStats,
    MatchCondition,
    QueryFilter,
    RangeCondition,
    VectorHit,
)


@dataclass
class FakePoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _matches(payload: dict[str, Any], f: QueryFilter | None) -> bool:
    if f is None:
        return True
    if not all(_match_ok(payload.get(c.key), c) for c in f.must_match):
        return False
    return all(_range_ok(payload.get(c.key), c) for c in f.must_range)


def _match_ok(value: Any, cond: MatchCondition) -> bool:
    if isinstance(value, list):
        return any(v in cond.values for v in value)
    return value in cond.values


def _range_ok(value: Any, cond: RangeCondition) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    return (cond.gte is None or value >= cond.gte) and (
        cond.lte is None or value <= cond.lte
    )


@dataclass
class InMemoryVectorRepository:
    """Brute-force cosine search over in-memory points. Read-only."""

    collections: dict[str, list[FakePoint]] = field(default_factory=dict)
    distance: str = "Cosine"

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
        points = self.collections.get(collection, [])
        scored: list[VectorHit] = []
        for point in points:
            if not _matches(point.payload, query_filter):
                continue
            score = _cosine(vector, point.vector)
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append(
                VectorHit(
                    id=point.id,
                    score=score,
                    payload=dict(point.payload),
                    collection=collection,
                )
            )
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]

    async def retrieve(self, *, collection: str, ids: list[str]) -> list[VectorHit]:
        wanted = set(ids)
        return [
            VectorHit(id=p.id, score=0.0, payload=dict(p.payload), collection=collection)
            for p in self.collections.get(collection, [])
            if p.id in wanted
        ]

    async def scroll(
        self, *, collection: str, scroll_filter: QueryFilter | None, limit: int
    ) -> list[VectorHit]:
        out: list[VectorHit] = []
        for p in self.collections.get(collection, []):
            if _matches(p.payload, scroll_filter):
                out.append(
                    VectorHit(id=p.id, score=0.0, payload=dict(p.payload), collection=collection)
                )
            if len(out) >= limit:
                break
        return out

    async def collection_exists(self, collection: str) -> bool:
        return collection in self.collections

    async def collection_stats(self, collection: str) -> CollectionStats:
        points = self.collections.get(collection, [])
        dims = len(points[0].vector) if points else None
        return CollectionStats(
            name=collection,
            vector_dimensions=dims,
            distance=self.distance,
            points_count=len(points),
            vector_sizes={"": dims} if dims else {},
        )


@dataclass
class InMemoryMetadataRepository:
    """Returns pre-seeded metadata rows. Read-only."""

    rows: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    healthy: bool = True

    async def fetch_metadata(
        self, *, collection: str, keys: list[str]
    ) -> dict[str, dict[str, Any]]:
        coll_rows = self.rows.get(collection, {})
        return {key: coll_rows[key] for key in keys if key in coll_rows}

    async def health(self) -> bool:
        return self.healthy
