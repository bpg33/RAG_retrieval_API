"""Unit tests for near-duplicate version collapsing."""

from __future__ import annotations

from datetime import UTC, datetime

from synology_rag.domain.models import RetrievedChunk
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.versions import collapse_versions

_LONG = "the programme identified recurring implementation risks and data quality issues"


def _cand(
    *,
    doc: str,
    filename: str,
    score: float,
    text: str = _LONG,
    modified: datetime | None = None,
) -> Candidate:
    return Candidate(
        chunk=RetrievedChunk(
            chunk_id=f"c-{doc}",
            document_id=doc,
            text=text,
            score=score,
            rank=0,
            collection="documents",
            filename=filename,
            modified_at=modified,
        )
    )


def test_collapses_filename_versions_keeping_latest() -> None:
    cands = [
        _cand(doc="d3", filename="Board deck v3.pptx", score=0.90,
              modified=datetime(2021, 3, 1, tzinfo=UTC)),
        _cand(doc="d5", filename="Board deck v5.pptx", score=0.85,
              modified=datetime(2021, 5, 1, tzinfo=UTC)),
        _cand(doc="d2", filename="Board deck v2.pptx", score=0.80,
              modified=datetime(2021, 2, 1, tzinfo=UTC)),
    ]
    kept, collapsed = collapse_versions(cands, similarity_threshold=0.9)
    assert collapsed == 2
    assert len(kept) == 1
    assert kept[0].chunk.filename == "Board deck v5.pptx"  # most recent
    assert kept[0].chunk.score == 0.90  # family's best score preserved for ranking


def test_distinct_documents_not_collapsed() -> None:
    cands = [
        _cand(doc="d1", filename="Budget 2020.xlsx", score=0.9, text="annual budget figures 2020"),
        _cand(doc="d2", filename="Strategy memo.docx", score=0.8, text="market strategy overview"),
    ]
    kept, collapsed = collapse_versions(cands, similarity_threshold=0.9)
    assert collapsed == 0
    assert len(kept) == 2


def test_year_suffixes_are_not_treated_as_versions() -> None:
    # "Budget 2020" vs "Budget 2021" are different documents, not versions.
    cands = [
        _cand(doc="d1", filename="Budget 2020.xlsx", score=0.9, text="alpha bravo charlie delta"),
        _cand(doc="d2", filename="Budget 2021.xlsx", score=0.8, text="echo foxtrot golf hotel"),
    ]
    kept, collapsed = collapse_versions(cands, similarity_threshold=0.9)
    assert collapsed == 0
    assert len(kept) == 2


def test_collapses_by_text_similarity_without_version_names() -> None:
    cands = [
        _cand(doc="d1", filename="report-a.pdf", score=0.9),
        _cand(doc="d2", filename="report-b.pdf", score=0.7),  # same text, different file
    ]
    kept, collapsed = collapse_versions(cands, similarity_threshold=0.9)
    assert collapsed == 1
    assert len(kept) == 1


def test_short_text_not_collapsed_by_text_signal() -> None:
    cands = [
        _cand(doc="d1", filename="a.pdf", score=0.9, text="TRANSFORMATION"),
        _cand(doc="d2", filename="b.pdf", score=0.7, text="TRANSFORMATION"),
    ]
    kept, collapsed = collapse_versions(cands, similarity_threshold=0.9)
    assert collapsed == 0  # too short to confidently call a duplicate
    assert len(kept) == 2


def test_same_document_not_collapsed() -> None:
    # Two distinct chunks of the SAME document must both survive.
    a = _cand(doc="d1", filename="a.pdf", score=0.9, text="intro alpha bravo charlie delta echo")
    b = _cand(doc="d1", filename="a.pdf", score=0.8, text="intro alpha bravo charlie delta echo")
    kept, collapsed = collapse_versions([a, b], similarity_threshold=0.9)
    assert collapsed == 0
    assert len(kept) == 2
