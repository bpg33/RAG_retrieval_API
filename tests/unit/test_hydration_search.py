"""End-to-end search when chunk text lives in PostgreSQL (like the real index).

Mirrors the RAG index handoff: Qdrant holds vectors + metadata only; the chunk
text and liveness live in PostgreSQL, keyed by chunk_id. Search must hydrate text
from Postgres and drop chunks whose row is absent (removed/superseded).
"""

from __future__ import annotations

from synology_rag.config import (
    CollectionMapping,
    MetadataSource,
    PayloadMapping,
    PostgresCollectionMapping,
    SchemaMapping,
)
from synology_rag.domain.models import SearchRequest
from synology_rag.retrieval.service import RetrievalService
from tests.conftest import make_settings
from tests.fakes import FakePoint, InMemoryMetadataRepository, InMemoryVectorRepository

DIMS = 64


def _mapping() -> SchemaMapping:
    coll = CollectionMapping(
        description="chunks",
        metadata_source=MetadataSource.BOTH,
        payload=PayloadMapping(
            text=None,  # text is NOT in Qdrant
            document_id="document_id",
            chunk_id="chunk_id",
            page_number="page_or_slide_number",
            file_type="file_type",
        ),
        postgres=PostgresCollectionMapping(
            schema="public",
            table="rag_chunk_hydration_v",
            lookup_key="chunk_id",
            key_column="chunk_id",
            columns={"text": "text_display", "filename": "file_name", "title": "title"},
            drop_if_missing=True,
        ),
    )
    return SchemaMapping(collections={"knowledge_chunks": coll})


async def _service(embedder):
    settings = make_settings(
        qdrant_allowed_collections="knowledge_chunks",
        startup_verify_collections=False,
    )
    mapping = _mapping()

    points = [
        FakePoint(
            id="pt-1",
            vector=await embedder.embed_query("implementation risks data quality scope creep"),
            payload={
                "chunk_id": "chunk-live",
                "document_id": "doc-1",
                "page_or_slide_number": 8,
                "file_type": "pdf",
            },
        ),
        FakePoint(
            id="pt-2",
            vector=await embedder.embed_query("recommendations mitigate asset tagging"),
            payload={
                "chunk_id": "chunk-removed",  # vector lingers but PG row is gone
                "document_id": "doc-1",
                "page_or_slide_number": 9,
                "file_type": "pdf",
            },
        ),
    ]
    vector_repo = InMemoryVectorRepository(collections={"knowledge_chunks": points})
    metadata_repo = InMemoryMetadataRepository(
        rows={
            "knowledge_chunks": {
                # Only the live chunk has a row (the view excludes removed files).
                "chunk-live": {
                    "text": "The programme identified recurring implementation risks.",
                    "filename": "Asset Tagging Review.pdf",
                    "title": "Asset Tagging Review",
                },
            }
        }
    )
    return RetrievalService(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=metadata_repo,
    )


async def test_text_is_hydrated_from_postgres(embedder) -> None:
    service = await _service(embedder)
    response = await service.search(
        SearchRequest(
            query="recurring implementation risks data quality scope creep",
            include_neighbours=False,
        )
    )
    assert response.results
    top = response.results[0]
    assert top.chunk_id == "chunk-live"
    assert "recurring implementation risks" in top.text  # came from Postgres
    assert top.filename == "Asset Tagging Review.pdf"
    assert top.page_number == 8  # from Qdrant payload
    # citation display name from hydrated filename
    assert response.citations[0].display_name == "Asset Tagging Review.pdf"


async def test_removed_chunk_is_dropped(embedder) -> None:
    service = await _service(embedder)
    response = await service.search(
        SearchRequest(query="recommendations mitigate asset tagging", include_neighbours=False)
    )
    ids = [c.chunk_id for c in response.results]
    assert "chunk-removed" not in ids  # liveness: no PG row -> dropped
    assert any("no longer present" in w for w in response.warnings)
