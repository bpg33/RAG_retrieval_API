"""Unit tests for PostgreSQL metadata enrichment and graceful degradation."""

from __future__ import annotations

from typing import Any

from synology_rag.config import (
    CollectionMapping,
    MetadataSource,
    PayloadMapping,
    PostgresCollectionMapping,
    SchemaMapping,
)
from synology_rag.domain.models import RetrievedChunk
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.metadata import enrich_candidates
from tests.fakes import InMemoryMetadataRepository


def _mapping(source: MetadataSource) -> SchemaMapping:
    coll = CollectionMapping(
        metadata_source=source,
        payload=PayloadMapping(text="text", document_id="document_id"),
        postgres=PostgresCollectionMapping(
            schema="public",
            table="docs_v",
            document_id_column="document_id",
            columns={"filename": "filename", "title": "title"},
        )
        if source is not MetadataSource.QDRANT
        else None,
    )
    return SchemaMapping(collections={"documents": coll})


def _candidate(document_id: str) -> Candidate:
    return Candidate(
        chunk=RetrievedChunk(
            chunk_id="c1",
            document_id=document_id,
            text="body",
            score=1.0,
            rank=1,
            collection="documents",
        )
    )


async def test_enrichment_fills_missing_fields() -> None:
    mapping = _mapping(MetadataSource.BOTH)
    repo = InMemoryMetadataRepository(
        rows={"documents": {"doc-1": {"filename": "A.pdf", "title": "The A Report"}}}
    )
    cand = _candidate("doc-1")
    warnings = await enrich_candidates([cand], mapping, repo)
    assert warnings == []
    assert cand.chunk.filename == "A.pdf"
    assert cand.chunk.title == "The A Report"


async def test_enrichment_does_not_overwrite_present_fields() -> None:
    mapping = _mapping(MetadataSource.BOTH)
    repo = InMemoryMetadataRepository(
        rows={"documents": {"doc-1": {"filename": "FromPG.pdf"}}}
    )
    cand = _candidate("doc-1")
    cand.chunk.filename = "FromQdrant.pdf"
    await enrich_candidates([cand], mapping, repo)
    assert cand.chunk.filename == "FromQdrant.pdf"  # gap-fill only


async def test_qdrant_only_source_skips_database() -> None:
    mapping = _mapping(MetadataSource.QDRANT)

    class ExplodingRepo:
        async def fetch_metadata(self, **_: Any) -> dict[str, dict[str, Any]]:
            raise AssertionError("must not be called for qdrant-only collections")

        async def health(self) -> bool:
            return True

    cand = _candidate("doc-1")
    warnings = await enrich_candidates([cand], mapping, ExplodingRepo())
    assert warnings == []


async def test_missing_repo_degrades_with_warning() -> None:
    mapping = _mapping(MetadataSource.BOTH)
    cand = _candidate("doc-1")
    warnings = await enrich_candidates([cand], mapping, None)
    assert any("not configured" in w for w in warnings)


async def test_repo_error_degrades_gracefully() -> None:
    mapping = _mapping(MetadataSource.BOTH)

    class FailingRepo:
        async def fetch_metadata(self, **_: Any) -> dict[str, dict[str, Any]]:
            raise RuntimeError("db down")

        async def health(self) -> bool:
            return False

    cand = _candidate("doc-1")
    warnings = await enrich_candidates([cand], mapping, FailingRepo())
    assert any("temporarily" in w for w in warnings)
    # The chunk is unchanged; we degrade rather than fabricate.
    assert cand.chunk.filename is None
