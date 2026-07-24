"""MCP tool contract tests.

Verifies the tool functions produce equivalent results to the REST layer and
that only the four approved read-only tools are exposed.
"""

from __future__ import annotations

import pytest

from synology_rag.mcp import tools
from synology_rag.mcp.server import build_mcp
from synology_rag.retrieval.service import RetrievalService

pytestmark = pytest.mark.contract

APPROVED_TOOLS = {
    "search_documents",
    "get_document_metadata",
    "get_chunk_context",
    "list_document_collections",
}


async def test_search_documents_returns_citations(service: RetrievalService) -> None:
    result = await tools.search_documents(
        service,
        query="poor data quality and scope creep implementation risks",
        limit=3,
        include_neighbours=False,
    )
    assert result["result_count"] >= 1
    assert result["results"][0]["chunk_id"] == "chunk-1b"
    assert result["results"][0]["citation"] == "src-1"
    assert result["citations"][0]["display_name"] == "Asset Tagging Programme Review.pdf"


async def test_search_documents_unknown_collection_returns_error(
    service: RetrievalService,
) -> None:
    result = await tools.search_documents(service, query="x", collections=["nope"])
    assert result["error"]["code"] == "unknown_collection"


async def test_get_chunk_context_tool(service: RetrievalService) -> None:
    result = await tools.get_chunk_context(
        service, chunk_id="chunk-1b", neighbours_before=1, neighbours_after=1
    )
    ids = [r["chunk_id"] for r in result["results"]]
    assert ids == ["chunk-1a", "chunk-1b", "chunk-1c"]


async def test_list_collections_tool(service: RetrievalService) -> None:
    result = await tools.list_document_collections(service)
    assert [c["name"] for c in result["collections"]] == ["documents"]


async def test_only_approved_tools_exposed(container) -> None:
    mcp = build_mcp(container)
    listed = {t.name for t in await mcp.list_tools()}
    assert listed == APPROVED_TOOLS


async def test_no_prohibited_tools_exposed(container) -> None:
    mcp = build_mcp(container)
    listed = {t.name for t in await mcp.list_tools()}
    prohibited = {"execute_sql", "upsert", "delete", "write_file", "run_shell", "reindex"}
    assert not (listed & prohibited)


async def test_rest_and_mcp_agree(service: RetrievalService) -> None:
    """REST and MCP must produce equivalent retrieval results (same engine)."""
    from synology_rag.domain.models import SearchRequest

    query = "poor data quality and scope creep implementation risks"
    rest = await service.search(SearchRequest(query=query, limit=3, include_neighbours=False))
    mcp_result = await tools.search_documents(
        service, query=query, limit=3, include_neighbours=False
    )
    rest_ids = [c.chunk_id for c in rest.results]
    mcp_ids = [r["chunk_id"] for r in mcp_result["results"]]
    assert rest_ids == mcp_ids
