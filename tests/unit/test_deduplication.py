"""Unit tests for deduplication."""

from __future__ import annotations

from synology_rag.domain.models import RetrievedChunk
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.deduplication import deduplicate


def _cand(
    chunk_id: str, doc: str, text: str, score: float, active: bool | None = None
) -> Candidate:
    return Candidate(
        chunk=RetrievedChunk(
            chunk_id=chunk_id,
            document_id=doc,
            text=text,
            score=score,
            rank=0,
            collection="documents",
        ),
        active=active,
    )


def test_exact_duplicate_chunk_id_removed() -> None:
    cands = [_cand("c1", "d1", "hello world", 0.9), _cand("c1", "d1", "hello world", 0.5)]
    result = deduplicate(cands)
    assert len(result) == 1
    assert result[0].chunk.score == 0.9


def test_identical_text_removed() -> None:
    cands = [_cand("c1", "d1", "Same text.", 0.9), _cand("c2", "d2", "same   text.", 0.4)]
    result = deduplicate(cands)
    assert len(result) == 1


def test_contained_passage_removed_same_document() -> None:
    long = _cand("c1", "d1", "The quick brown fox jumps over the lazy dog.", 0.8)
    short = _cand("c2", "d1", "quick brown fox", 0.7)
    result = deduplicate([long, short])
    assert {c.chunk.chunk_id for c in result} == {"c1"}


def test_distinct_passages_same_document_kept() -> None:
    a = _cand("c1", "d1", "Introduction and background of the report.", 0.8)
    b = _cand("c2", "d1", "Conclusions and next steps for the team.", 0.7)
    result = deduplicate([a, b])
    assert len(result) == 2


def test_superseded_inactive_version_dropped() -> None:
    active = _cand("c1", "d1", "Latest content A.", 0.8, active=True)
    inactive = _cand("c2", "d1", "Old content B.", 0.9, active=False)
    result = deduplicate([active, inactive])
    assert {c.chunk.chunk_id for c in result} == {"c1"}


def test_inactive_kept_when_no_active_sibling() -> None:
    inactive = _cand("c1", "d1", "Only content.", 0.9, active=False)
    result = deduplicate([inactive])
    assert len(result) == 1
