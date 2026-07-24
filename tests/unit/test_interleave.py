"""Regression test: neighbour ordering must not crash on missing sequences."""

from __future__ import annotations

from synology_rag.domain.models import RetrievedChunk
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.service import _interleave


def _primary(chunk_id: str, seq: int) -> Candidate:
    return Candidate(
        chunk=RetrievedChunk(
            chunk_id=chunk_id, document_id="d", text="p", score=1.0, rank=1, collection="documents"
        ),
        sequence=seq,
    )


def _neighbour(chunk_id: str, parent: str, seq: int | None) -> Candidate:
    return Candidate(
        chunk=RetrievedChunk(
            chunk_id=chunk_id,
            document_id="d",
            text="n",
            score=0.0,
            rank=1,
            collection="documents",
            is_neighbour=True,
            parent_result_chunk_id=parent,
        ),
        sequence=seq,
    )


def test_interleave_orders_before_and_after() -> None:
    primary = _primary("p", 5)
    neighbours = [_neighbour("n-before", "p", 4), _neighbour("n-after", "p", 6)]
    ordered = _interleave([primary], neighbours)
    assert [c.chunk_id for c in ordered] == ["n-before", "p", "n-after"]


def test_interleave_handles_multiple_none_sequences_without_crashing() -> None:
    # Two neighbours with unknown sequence previously raised TypeError (None < None).
    primary = _primary("p", 5)
    neighbours = [
        _neighbour("n1", "p", None),
        _neighbour("n2", "p", None),
    ]
    ordered = _interleave([primary], neighbours)
    ids = [c.chunk_id for c in ordered]
    # Primary first (None-sequence neighbours are treated as "after"), then the two.
    assert ids[0] == "p"
    assert set(ids[1:]) == {"n1", "n2"}
