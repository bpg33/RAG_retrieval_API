"""Unit tests for PostgreSQL hydration, chunk-keyed lookup, and liveness."""

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


def _mapping(
    source: MetadataSource,
    *,
    lookup_key: str = "document_id",
    key_column: str = "document_id",
    drop_if_missing: bool = False,
) -> SchemaMapping:
    pg = (
        PostgresCollectionMapping(
            schema="public",
            table="docs_v",
            lookup_key=lookup_key,  # type: ignore[arg-type]
            key_column=key_column,
            columns={"filename": "filename", "title": "title", "text": "text_display"},
            drop_if_missing=drop_if_missing,
        )
        if source is not MetadataSource.QDRANT
        else None
    )
    coll = CollectionMapping(
        metadata_source=source,
        payload=PayloadMapping(text="text", document_id="document_id", chunk_id="chunk_id"),
        postgres=pg,
    )
    return SchemaMapping(collections={"documents": coll})


def _candidate(*, chunk_id: str = "c1", document_id: str = "doc-1", text: str = "") -> Candidate:
    return Candidate(
        chunk=RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            text=text,
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
    cand = _candidate()
    kept, warnings = await enrich_candidates([cand], mapping, repo)
    assert warnings == []
    assert kept == [cand]
    assert cand.chunk.filename == "A.pdf"
    assert cand.chunk.title == "The A Report"


async def test_chunk_keyed_hydration_fills_text() -> None:
    mapping = _mapping(MetadataSource.POSTGRES, lookup_key="chunk_id", key_column="chunk_id")
    repo = InMemoryMetadataRepository(
        rows={"documents": {"c1": {"text": "the hydrated chunk body", "filename": "A.pdf"}}}
    )
    cand = _candidate(chunk_id="c1", text="")
    kept, _ = await enrich_candidates([cand], mapping, repo)
    assert kept == [cand]
    assert cand.chunk.text == "the hydrated chunk body"


async def test_drop_if_missing_enforces_liveness() -> None:
    mapping = _mapping(
        MetadataSource.POSTGRES,
        lookup_key="chunk_id",
        key_column="chunk_id",
        drop_if_missing=True,
    )
    # 'removed' chunk c2 has no row in the (liveness-filtered) view.
    repo = InMemoryMetadataRepository(rows={"documents": {"c1": {"text": "live"}}})
    live = _candidate(chunk_id="c1")
    dead = _candidate(chunk_id="c2")
    kept, warnings = await enrich_candidates([live, dead], mapping, repo)
    assert kept == [live]
    assert any("no longer present" in w for w in warnings)


async def test_missing_row_kept_when_drop_disabled() -> None:
    mapping = _mapping(MetadataSource.BOTH, lookup_key="chunk_id", key_column="chunk_id")
    repo = InMemoryMetadataRepository(rows={"documents": {}})
    cand = _candidate(chunk_id="c9")
    kept, _ = await enrich_candidates([cand], mapping, repo)
    assert kept == [cand]  # not dropped when drop_if_missing is False


async def test_enrichment_does_not_overwrite_present_fields() -> None:
    mapping = _mapping(MetadataSource.BOTH)
    repo = InMemoryMetadataRepository(rows={"documents": {"doc-1": {"filename": "FromPG.pdf"}}})
    cand = _candidate()
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

    cand = _candidate()
    kept, warnings = await enrich_candidates([cand], mapping, ExplodingRepo())
    assert kept == [cand]
    assert warnings == []


async def test_missing_repo_degrades_with_warning() -> None:
    mapping = _mapping(MetadataSource.BOTH)
    cand = _candidate()
    kept, warnings = await enrich_candidates([cand], mapping, None)
    assert kept == [cand]
    assert any("not configured" in w for w in warnings)


async def test_repo_error_degrades_gracefully() -> None:
    mapping = _mapping(MetadataSource.BOTH)

    class FailingRepo:
        async def fetch_metadata(self, **_: Any) -> dict[str, dict[str, Any]]:
            raise RuntimeError("db down")

        async def health(self) -> bool:
            return False

    cand = _candidate()
    kept, warnings = await enrich_candidates([cand], mapping, FailingRepo())
    assert kept == [cand]  # degrade, do not fabricate or drop
    assert any("temporarily" in w for w in warnings)
    assert cand.chunk.filename is None
