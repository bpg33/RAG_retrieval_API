"""Neighbour expansion.

For each primary result, optionally fetch adjacent chunks from the *same
document*, identified strictly through explicit numeric sequence metadata -
never by assuming lexical chunk-id ordering. Neighbours are marked, de-duplicated
against primary hits and each other, and carry their parent's rank. They do not
displace primary results.
"""

from __future__ import annotations

from synology_rag.config import SchemaMapping
from synology_rag.domain.ports import MatchCondition, QueryFilter, RangeCondition, VectorRepository
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.metadata import chunk_from_hit


async def expand_neighbours(
    primaries: list[Candidate],
    *,
    repo: VectorRepository,
    mapping: SchemaMapping,
    neighbours_before: int,
    neighbours_after: int,
) -> list[Candidate]:
    if neighbours_before <= 0 and neighbours_after <= 0:
        return []

    taken: set[tuple[str, str]] = {
        (c.chunk.collection, c.chunk.chunk_id) for c in primaries
    }
    neighbours: list[Candidate] = []

    for parent in primaries:
        seq = parent.sequence
        if seq is None:
            continue  # cannot order safely without explicit sequence metadata
        coll = mapping.for_collection(parent.chunk.collection)
        seq_key = coll.payload.sequence
        doc_key = coll.payload.document_id
        if not seq_key or not doc_key:
            continue

        low = seq - neighbours_before
        high = seq + neighbours_after
        scroll_filter = QueryFilter(
            must_match=[MatchCondition(key=doc_key, values=[parent.chunk.document_id])],
            must_range=[RangeCondition(key=seq_key, gte=low, lte=high)],
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
            cand.chunk.is_neighbour = True
            cand.chunk.parent_result_chunk_id = parent.chunk.chunk_id
            cand.chunk.rank = parent.chunk.rank
            cand.chunk.score = 0.0
            neighbours.append(cand)

    return neighbours
