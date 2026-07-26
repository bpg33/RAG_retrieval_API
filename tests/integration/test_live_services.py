"""Integration tests against live Qdrant/PostgreSQL/embedding services.

Skipped unless RUN_INTEGRATION=1 is set and the environment is configured. These
never perform destructive operations - reads only.
"""

from __future__ import annotations

import os

import pytest

from synology_rag.domain.models import SearchRequest

pytestmark = pytest.mark.integration

_RUN = os.environ.get("RUN_INTEGRATION") == "1"
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _RUN, reason="RUN_INTEGRATION!=1")]


@pytest.fixture
async def live_container():
    from synology_rag.container import build_container

    container = build_container()
    await container.startup()
    try:
        yield container
    finally:
        await container.shutdown()


async def test_collections_reachable(live_container) -> None:
    infos = await live_container.service.list_collections()
    assert infos
    for info in infos:
        assert info.vector_dimensions == live_container.settings.embedding_dimensions


async def test_live_search_returns_results(live_container) -> None:
    query = os.environ.get("INTEGRATION_QUERY", "test")
    response = await live_container.service.search(SearchRequest(query=query, limit=5))
    # We cannot assert specific documents, only that the pipeline runs and cites.
    assert response.search_id
    for chunk in response.results:
        assert chunk.document_id
    for citation in response.citations:
        assert citation.display_name


async def test_readiness_ok(live_container) -> None:
    deps = await live_container.service.readiness()
    assert deps["qdrant"] is True
    assert deps["embedding"] is True
