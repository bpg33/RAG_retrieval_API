"""Compact, bounded formatting of engine results for MCP clients.

MCP responses are useful to an LLM but bounded: they never include database
passwords, connection strings, sensitive absolute paths, unrelated raw rows, or
entire documents. Each passage carries a stable citation label linking it to the
assembled citation list.
"""

from __future__ import annotations

from typing import Any

from synology_rag.domain.models import (
    Citation,
    CollectionInfo,
    DocumentMetadata,
    RetrievedChunk,
    SearchResponse,
)


def _chunk_locator(chunk: RetrievedChunk) -> str | None:
    if chunk.page_number is not None:
        return f"Page {chunk.page_number}"
    if chunk.slide_number is not None:
        return f"Slide {chunk.slide_number}"
    if chunk.sheet_name:
        return f"Sheet '{chunk.sheet_name}'"
    if chunk.section:
        return f"Section: {chunk.section}"
    return None


def _citation_index(citations: list[Citation]) -> dict[str, str]:
    return {c.document_id: c.citation_id for c in citations}


def format_search_response(response: SearchResponse) -> dict[str, Any]:
    citation_of = _citation_index(response.citations)
    results = [
        {
            "rank": chunk.rank,
            "text": chunk.text,
            "source": chunk.filename or chunk.title or chunk.document_id,
            "locator": _chunk_locator(chunk),
            "source_uri": chunk.source_uri,
            "document_id": chunk.document_id,
            "chunk_id": chunk.chunk_id,
            "score": round(chunk.score, 4),
            "is_neighbour": chunk.is_neighbour,
            "citation": citation_of.get(chunk.document_id),
            "truncated": chunk.truncated,
        }
        for chunk in response.results
    ]
    citations = [
        {
            "citation_id": c.citation_id,
            "display_name": c.display_name,
            "locator": c.locator,
            "source_uri": c.source_uri,
            "document_id": c.document_id,
        }
        for c in response.citations
    ]
    return {
        "query": response.query,
        "search_id": response.search_id,
        "result_count": len(response.results),
        "elapsed_ms": response.elapsed_ms,
        "truncated": response.truncated,
        "warnings": response.warnings,
        "results": results,
        "citations": citations,
    }


def format_document(doc: DocumentMetadata) -> dict[str, Any]:
    return {
        "document_id": doc.document_id,
        "display_name": doc.display_name,
        "title": doc.title,
        "file_type": doc.file_type,
        "source_uri": doc.source_uri,
        "modified_at": doc.modified_at.isoformat() if doc.modified_at else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "collection": doc.collection,
    }


def format_collections(infos: list[CollectionInfo]) -> dict[str, Any]:
    return {
        "collections": [
            {
                "name": info.name,
                "description": info.description,
                "vector_dimensions": info.vector_dimensions,
                "distance": info.distance,
                "points_count": info.points_count,
            }
            for info in infos
        ]
    }


def format_error(code: str, message: str, retryable: bool) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "retryable": retryable}}
