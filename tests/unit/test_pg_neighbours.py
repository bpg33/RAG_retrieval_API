"""End-to-end Postgres-based neighbour expansion.

For indexes whose chunk order lives in PostgreSQL (chunks.chunk_index), adjacent
chunks are fetched from PostgreSQL, not Qdrant.
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


def _mapping() -> SchemaMapping:
    coll = CollectionMapping(
        metadata_source=MetadataSource.BOTH,
        neighbour_source="postgres",
        payload=PayloadMapping(text=None, document_id="document_id", chunk_id="chunk_id"),
        postgres=PostgresCollectionMapping(
            schema="public",
            table="rag_chunks_v",
            lookup_key="chunk_id",
            key_column="chunk_id",
            document_id_column="document_id",
            columns={"text": "text_display", "sequence": "chunk_index"},
            drop_if_missing=False,
        ),
    )
    return SchemaMapping(collections={"kc": coll})


async def _service(embedder):
    settings = make_settings(
        qdrant_allowed_collections="kc", startup_verify_collections=False
    )
    primary = FakePoint(
        id="pt-5",
        vector=await embedder.embed_query("transformation programme implementation risks"),
        payload={"chunk_id": "c5", "document_id": "d1"},
    )
    vector_repo = InMemoryVectorRepository(collections={"kc": [primary]})
    metadata_repo = InMemoryMetadataRepository(
        rows={"kc": {"c5": {"text": "the primary chunk about transformation", "sequence": 5}}},
        neighbour_rows={
            "kc": [
                {"document_id": "d1", "chunk_id": "c4", "sequence": 4, "text": "the chunk before"},
                {"document_id": "d1", "chunk_id": "c5", "sequence": 5, "text": "the primary chunk"},
                {"document_id": "d1", "chunk_id": "c6", "sequence": 6, "text": "the chunk after"},
            ]
        },
    )
    return RetrievalService(
        settings=settings,
        mapping=_mapping(),
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=metadata_repo,
    )


async def test_postgres_neighbours_surround_primary(embedder) -> None:
    service = await _service(embedder)
    response = await service.search(
        SearchRequest(
            query="transformation programme implementation risks",
            include_neighbours=True,
            neighbours_before=1,
            neighbours_after=1,
        )
    )
    ids = [c.chunk_id for c in response.results]
    assert ids == ["c4", "c5", "c6"]  # before, primary, after (by chunk_index)
    primary = next(c for c in response.results if not c.is_neighbour)
    assert primary.chunk_id == "c5"
    neighbours = [c for c in response.results if c.is_neighbour]
    assert {n.chunk_id for n in neighbours} == {"c4", "c6"}
    assert all(n.parent_result_chunk_id == "c5" for n in neighbours)
    assert all(n.text for n in neighbours)  # neighbour text came from PostgreSQL


async def test_no_neighbours_when_disabled(embedder) -> None:
    service = await _service(embedder)
    response = await service.search(
        SearchRequest(query="transformation programme", include_neighbours=False)
    )
    assert [c.chunk_id for c in response.results] == ["c5"]
