"""End-to-end retrieval pipeline tests using in-memory fakes."""

from __future__ import annotations

import pytest

from synology_rag.domain.errors import UnknownCollectionError, UnsupportedFilterError
from synology_rag.domain.models import SearchRequest
from synology_rag.retrieval.service import RetrievalService


async def test_search_returns_relevant_passage_first(service: RetrievalService) -> None:
    response = await service.search(
        SearchRequest(
            query="poor data quality and scope creep recurring implementation risks",
            limit=3,
            include_neighbours=False,
        )
    )
    assert response.results, "expected at least one result"
    top = response.results[0]
    assert top.chunk_id == "chunk-1b"
    assert top.rank == 1
    assert top.page_number == 8
    assert top.section == "Implementation risks"
    assert response.search_id == "test-000001"


async def test_search_assembles_citation(service: RetrievalService) -> None:
    response = await service.search(
        SearchRequest(query="asset tagging implementation risks", limit=3, include_neighbours=False)
    )
    assert response.citations
    citation = response.citations[0]
    assert citation.citation_id == "src-1"
    assert citation.display_name == "Asset Tagging Programme Review.pdf"
    assert citation.locator is not None and "Page" in citation.locator


async def test_neighbours_are_marked_and_adjacent(service: RetrievalService) -> None:
    response = await service.search(
        SearchRequest(
            query="poor data quality and scope creep recurring implementation risks",
            limit=1,
            include_neighbours=True,
            neighbours_before=1,
            neighbours_after=1,
        )
    )
    ids = [c.chunk_id for c in response.results]
    # chunk-1b is the primary; 1a precedes and 1c follows it.
    assert ids == ["chunk-1a", "chunk-1b", "chunk-1c"]
    primary = next(c for c in response.results if not c.is_neighbour)
    assert primary.chunk_id == "chunk-1b"
    neighbours = [c for c in response.results if c.is_neighbour]
    assert all(n.parent_result_chunk_id == "chunk-1b" for n in neighbours)


async def test_file_type_filter_limits_results(service: RetrievalService) -> None:
    response = await service.search(
        SearchRequest(
            query="budget figures finance",
            file_types=["xlsx"],
            include_neighbours=False,
        )
    )
    assert response.results
    assert all(c.file_type == "xlsx" for c in response.results)


async def test_unknown_collection_rejected(service: RetrievalService) -> None:
    with pytest.raises(UnknownCollectionError):
        await service.search(SearchRequest(query="x", collections=["secret_collection"]))


async def test_unsupported_filter_rejected(service: RetrievalService) -> None:
    with pytest.raises(UnsupportedFilterError):
        await service.search(
            SearchRequest(query="x", metadata_filters={"ssn": "123-45-6789"})
        )


async def test_empty_results_reported(service: RetrievalService) -> None:
    response = await service.search(
        SearchRequest(
            query="asset tagging",
            minimum_score=0.999,
            include_neighbours=False,
        )
    )
    assert response.results == []
    assert any("insufficient" in w for w in response.warnings)


async def test_get_chunk_context(service: RetrievalService) -> None:
    response = await service.get_chunk_context(
        "chunk-1b", neighbours_before=1, neighbours_after=1
    )
    ids = [c.chunk_id for c in response.results]
    assert ids == ["chunk-1a", "chunk-1b", "chunk-1c"]


async def test_get_document_metadata(service: RetrievalService) -> None:
    doc = await service.get_document_metadata("doc-1")
    assert doc.document_id == "doc-1"
    assert doc.display_name == "Asset Tagging Programme Review.pdf"
    assert doc.file_type == "pdf"


async def test_list_collections(service: RetrievalService) -> None:
    infos = await service.list_collections()
    assert [i.name for i in infos] == ["documents"]
    assert infos[0].vector_dimensions == 64
