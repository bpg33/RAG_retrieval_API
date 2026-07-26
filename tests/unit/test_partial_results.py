"""Partial-results behaviour when one of several collections is unavailable."""

from __future__ import annotations

import pytest

from synology_rag.config import CollectionMapping, PayloadMapping, SchemaMapping
from synology_rag.domain.errors import QdrantUnavailableError
from synology_rag.domain.models import SearchRequest
from synology_rag.domain.ports import VectorHit
from synology_rag.retrieval.service import RetrievalService
from tests.conftest import make_settings
from tests.fakes import InMemoryVectorRepository


class PartialRepo(InMemoryVectorRepository):
    """Vector repo that raises for a chosen set of collections."""

    def __init__(self, collections, failing: set[str]) -> None:
        super().__init__(collections=collections)
        self.failing = failing

    async def search(self, *, collection: str, **kwargs) -> list[VectorHit]:
        if collection in self.failing:
            raise QdrantUnavailableError("collection down")
        return await super().search(collection=collection, **kwargs)

    async def collection_exists(self, collection: str) -> bool:
        return True


def _two_collection_mapping() -> SchemaMapping:
    payload = PayloadMapping(text="text", document_id="document_id")
    return SchemaMapping(
        collections={
            "documents": CollectionMapping(payload=payload),
            "notes": CollectionMapping(payload=payload),
        }
    )


def _service(vector_repo, embedder, *, partial: bool) -> RetrievalService:
    settings = make_settings(
        qdrant_allowed_collections="documents,notes",
        partial_results_on_collection_error=partial,
        startup_verify_collections=False,
    )
    return RetrievalService(
        settings=settings,
        mapping=_two_collection_mapping(),
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=None,
    )


async def test_partial_results_returns_available_collection_with_warning(
    vector_repo, embedder
) -> None:
    repo = PartialRepo(collections=dict(vector_repo.collections), failing={"notes"})
    service = _service(repo, embedder, partial=True)
    response = await service.search(
        SearchRequest(query="asset tagging implementation risks", include_neighbours=False)
    )
    assert response.results  # documents still returned
    assert any("notes" in w and "unavailable" in w for w in response.warnings)


async def test_collection_error_fails_when_partial_disabled(
    vector_repo, embedder
) -> None:
    repo = PartialRepo(collections=dict(vector_repo.collections), failing={"notes"})
    service = _service(repo, embedder, partial=False)
    with pytest.raises(QdrantUnavailableError):
        await service.search(SearchRequest(query="asset tagging", include_neighbours=False))


async def test_all_collections_failing_raises_even_when_partial(
    vector_repo, embedder
) -> None:
    repo = PartialRepo(
        collections=dict(vector_repo.collections), failing={"documents", "notes"}
    )
    service = _service(repo, embedder, partial=True)
    with pytest.raises(QdrantUnavailableError):
        await service.search(SearchRequest(query="asset tagging", include_neighbours=False))
