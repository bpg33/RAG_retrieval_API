"""Neighbour expansion.

For each primary result, optionally fetch adjacent chunks from the *same
document*, identified strictly through explicit numeric sequence metadata - never
by assuming lexical chunk-id ordering. Neighbours are marked, de-duplicated
against primary hits and each other, and carry their parent's rank. They do not
displace primary results.

Two sources, chosen per collection via ``neighbour_source``:

* ``qdrant`` - adjacent chunks located by a sequence *payload key* (a scroll with
  a range filter);
* ``postgres`` - adjacent chunks located by a sequence *column* (for indexes
  whose chunk order lives only in PostgreSQL, e.g. ``chunks.chunk_index``).
"""

from __future__ import annotations

from synology_rag.config import SchemaMapping
from synology_rag.domain.ports import (
    MatchCondition,
    MetadataRepository,
    QueryFilter,
    RangeCondition,
    VectorRepository,
)
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.metadata import chunk_from_hit, chunk_from_row

_Taken = set[tuple[str, str]]


async def expand_neighbours(
    primaries: list[Candidate],
    *,
    vector_repo: VectorRepository,
    metadata_repo: MetadataRepository | None,
    mapping: SchemaMapping,
    neighbours_before: int,
    neighbours_after: int,
) -> list[Candidate]:
    if neighbours_before <= 0 and neighbours_after <= 0:
        return []

    qdrant_parents: list[Candidate] = []
    postgres_parents: list[Candidate] = []
    for parent in primaries:
        source = mapping.for_collection(parent.chunk.collection).neighbour_source
        (postgres_parents if source == "postgres" else qdrant_parents).append(parent)

    taken: _Taken = {(c.chunk.collection, c.chunk.chunk_id) for c in primaries}
    neighbours: list[Candidate] = []

    if qdrant_parents:
        neighbours.extend(
            await _expand_via_qdrant(
                qdrant_parents,
                repo=vector_repo,
                mapping=mapping,
                neighbours_before=neighbours_before,
                neighbours_after=neighbours_after,
                taken=taken,
            )
        )
    if postgres_parents and metadata_repo is not None:
        neighbours.extend(
            await _expand_via_postgres(
                postgres_parents,
                repo=metadata_repo,
                neighbours_before=neighbours_before,
                neighbours_after=neighbours_after,
                taken=taken,
            )
        )
    return neighbours


def _mark_neighbour(cand: Candidate, parent: Candidate) -> None:
    cand.chunk.is_neighbour = True
    cand.chunk.parent_result_chunk_id = parent.chunk.chunk_id
    cand.chunk.rank = parent.chunk.rank
    cand.chunk.score = 0.0


async def _expand_via_qdrant(
    parents: list[Candidate],
    *,
    repo: VectorRepository,
    mapping: SchemaMapping,
    neighbours_before: int,
    neighbours_after: int,
    taken: _Taken,
) -> list[Candidate]:
    neighbours: list[Candidate] = []
    for parent in parents:
        seq = parent.sequence
        if seq is None:
            continue  # cannot order safely without explicit sequence metadata
        coll = mapping.for_collection(parent.chunk.collection)
        seq_key = coll.payload.sequence
        doc_key = coll.payload.document_id
        if not seq_key or not doc_key:
            continue

        scroll_filter = QueryFilter(
            must_match=[MatchCondition(key=doc_key, values=[parent.chunk.document_id])],
            must_range=[
                RangeCondition(key=seq_key, gte=seq - neighbours_before, lte=seq + neighbours_after)
            ],
        )
        hits = await repo.scroll(
            collection=parent.chunk.collection,
            scroll_filter=scroll_filter,
            limit=neighbours_before + neighbours_after + 1,
        )
        for hit in hits:
            cand = chunk_from_hit(hit, coll)
            if cand.sequence == seq:
                continue  # the parent chunk itself
            key = (cand.chunk.collection, cand.chunk.chunk_id)
            if key in taken:
                continue
            taken.add(key)
            _mark_neighbour(cand, parent)
            neighbours.append(cand)
    return neighbours


async def _expand_via_postgres(
    parents: list[Candidate],
    *,
    repo: MetadataRepository,
    neighbours_before: int,
    neighbours_after: int,
    taken: _Taken,
) -> list[Candidate]:
    neighbours: list[Candidate] = []
    for parent in parents:
        seq = parent.sequence
        if seq is None:
            continue
        try:
            rows = await repo.fetch_neighbours(
                collection=parent.chunk.collection,
                document_id=parent.chunk.document_id,
                low=seq - neighbours_before,
                high=seq + neighbours_after,
            )
        except Exception:  # PostgresUnavailableError etc.; skip neighbours, keep primaries
            continue
        for row in rows:
            cand = chunk_from_row(row, parent.chunk.collection)
            if cand.sequence == seq:
                continue  # the parent chunk itself
            key = (cand.chunk.collection, cand.chunk.chunk_id)
            if key in taken:
                continue
            taken.add(key)
            _mark_neighbour(cand, parent)
            neighbours.append(cand)
    return neighbours
