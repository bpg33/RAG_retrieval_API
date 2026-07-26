"""Unit tests for citation assembly."""

from __future__ import annotations

from synology_rag.domain.models import RetrievedChunk
from synology_rag.retrieval.citations import build_citations


def _chunk(**kw: object) -> RetrievedChunk:
    base: dict[str, object] = {
        "chunk_id": "c",
        "document_id": "d",
        "text": "t",
        "score": 1.0,
        "rank": 1,
        "collection": "documents",
    }
    base.update(kw)
    return RetrievedChunk(**base)  # type: ignore[arg-type]


def test_one_citation_per_document() -> None:
    chunks = [
        _chunk(chunk_id="c1", document_id="d1", filename="A.pdf", page_number=8),
        _chunk(chunk_id="c2", document_id="d1", filename="A.pdf", page_number=9),
        _chunk(chunk_id="c3", document_id="d2", filename="B.pptx", slide_number=3),
    ]
    citations = build_citations(chunks)
    assert [c.citation_id for c in citations] == ["src-1", "src-2"]
    assert citations[0].chunk_ids == ["c1", "c2"]
    assert citations[0].locator == "Pages 8, 9"
    assert citations[1].locator == "Slide 3"


def test_display_name_falls_back_to_title_then_id() -> None:
    chunks = [_chunk(chunk_id="c1", document_id="d1", title="My Title")]
    assert build_citations(chunks)[0].display_name == "My Title"
    chunks = [_chunk(chunk_id="c1", document_id="only-id")]
    assert build_citations(chunks)[0].display_name == "only-id"


def test_locator_prefers_primary_over_neighbour() -> None:
    chunks = [
        _chunk(chunk_id="c1", document_id="d1", filename="A.pdf", page_number=8),
        _chunk(
            chunk_id="c2",
            document_id="d1",
            filename="A.pdf",
            page_number=7,
            is_neighbour=True,
            parent_result_chunk_id="c1",
        ),
    ]
    citation = build_citations(chunks)[0]
    # Locator derives from the primary chunk (page 8), not the neighbour.
    assert citation.locator == "Page 8"
    assert citation.chunk_ids == ["c1", "c2"]
