"""Unit tests for source-URI templating (openable document links)."""

from __future__ import annotations

from synology_rag.config import CollectionMapping, PayloadMapping, SourceUriTemplate
from synology_rag.domain.ports import VectorHit
from synology_rag.retrieval.metadata import chunk_from_hit


def _hit(payload: dict[str, object]) -> VectorHit:
    return VectorHit(id="pt-1", score=0.9, payload=payload, collection="documents")


def _coll(template: SourceUriTemplate) -> CollectionMapping:
    return CollectionMapping(
        payload=PayloadMapping(
            text="text",
            document_id="document_id",
            file_type="file_type",
            page_number="page",
        ),
        source_uri=template,
    )


def test_builds_unc_path_with_backslashes() -> None:
    coll = _coll(
        SourceUriTemplate(
            from_payload="source_path",
            strip_prefix="/data/",
            add_prefix="\\\\192.168.1.59\\share\\",
            separator="\\",
        )
    )
    hit = _hit(
        {
            "text": "body",
            "document_id": "d1",
            "file_type": "pptx",
            "source_path": "/data/knowledge_1/Board deck.pptx",
        }
    )
    cand = chunk_from_hit(hit, coll)
    assert cand.chunk.source_uri == "\\\\192.168.1.59\\share\\knowledge_1\\Board deck.pptx"


def test_pdf_page_anchor_appended_for_pdfs() -> None:
    coll = _coll(
        SourceUriTemplate(
            from_payload="source_path",
            strip_prefix="/data/",
            add_prefix="file:///mnt/share/",
            pdf_page_anchor=True,
        )
    )
    hit = _hit(
        {
            "text": "body",
            "document_id": "d1",
            "file_type": "pdf",
            "page": 8,
            "source_path": "/data/report.pdf",
        }
    )
    cand = chunk_from_hit(hit, coll)
    assert cand.chunk.source_uri == "file:///mnt/share/report.pdf#page=8"


def test_no_page_anchor_for_non_pdf() -> None:
    coll = _coll(
        SourceUriTemplate(
            from_payload="source_path", add_prefix="x/", pdf_page_anchor=True
        )
    )
    hit = _hit(
        {"text": "b", "document_id": "d1", "file_type": "pptx", "page": 3, "source_path": "a.pptx"}
    )
    cand = chunk_from_hit(hit, coll)
    assert cand.chunk.source_uri == "x/a.pptx"


def test_missing_source_path_yields_none() -> None:
    coll = _coll(SourceUriTemplate(from_payload="source_path", add_prefix="x/"))
    hit = _hit({"text": "b", "document_id": "d1", "file_type": "pdf"})
    cand = chunk_from_hit(hit, coll)
    assert cand.chunk.source_uri is None
