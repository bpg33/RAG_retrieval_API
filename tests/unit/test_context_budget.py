"""Unit tests for context-budget enforcement."""

from __future__ import annotations

from synology_rag.domain.models import RetrievedChunk
from synology_rag.retrieval.context_budget import apply_context_budget


def _chunk(chunk_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, document_id="d", text=text, score=1.0, rank=1, collection="documents"
    )


def test_total_chunk_cap() -> None:
    chunks = [_chunk(f"c{i}", "x") for i in range(30)]
    result = apply_context_budget(
        chunks, max_total_chunks=20, max_total_characters=100000, max_characters_per_chunk=0
    )
    assert len(result.chunks) == 20
    assert result.truncated is True


def test_per_chunk_cap_truncates_and_marks() -> None:
    chunks = [_chunk("c1", "abcdefghij")]
    result = apply_context_budget(
        chunks, max_total_chunks=20, max_total_characters=100000, max_characters_per_chunk=4
    )
    assert result.chunks[0].text == "abcd"
    assert result.chunks[0].truncated is True
    assert result.truncated is True


def test_total_character_budget_truncates_last_and_stops() -> None:
    chunks = [_chunk("c1", "a" * 30), _chunk("c2", "b" * 30), _chunk("c3", "c" * 30)]
    result = apply_context_budget(
        chunks, max_total_chunks=20, max_total_characters=45, max_characters_per_chunk=0
    )
    # c1 (30) fits, c2 truncated to 15, c3 dropped.
    assert result.chunks[0].text == "a" * 30
    assert result.chunks[1].text == "b" * 15
    assert result.chunks[1].truncated is True
    assert len(result.chunks) == 2
    assert result.truncated is True


def test_no_truncation_when_within_budget() -> None:
    chunks = [_chunk("c1", "short")]
    result = apply_context_budget(
        chunks, max_total_chunks=20, max_total_characters=1000, max_characters_per_chunk=0
    )
    assert result.truncated is False
    assert result.chunks[0].text == "short"
