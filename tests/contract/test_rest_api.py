"""REST API contract tests using FastAPI's TestClient over fake adapters."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def test_health_live(client) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_health_ready(client) -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["qdrant"] is True


def test_search_endpoint(client) -> None:
    resp = client.post(
        "/api/v1/search",
        json={
            "query": "poor data quality and scope creep implementation risks",
            "limit": 3,
            "include_neighbours": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["chunk_id"] == "chunk-1b"
    assert body["citations"][0]["display_name"] == "Asset Tagging Programme Review.pdf"
    assert resp.headers["X-Request-ID"]


def test_search_rejects_unknown_field(client) -> None:
    resp = client.post("/api/v1/search", json={"query": "x", "sql": "DROP TABLE"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_search_unknown_collection_returns_400(client) -> None:
    resp = client.post("/api/v1/search", json={"query": "x", "collections": ["nope"]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_collection"


def test_get_document(client) -> None:
    resp = client.get("/api/v1/documents/doc-1")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Asset Tagging Programme Review.pdf"


def test_get_missing_document_404(client) -> None:
    resp = client.get("/api/v1/documents/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "document_not_found"


def test_get_chunk_context(client) -> None:
    resp = client.get(
        "/api/v1/chunks/chunk-1b", params={"neighbours_before": 1, "neighbours_after": 1}
    )
    assert resp.status_code == 200
    ids = [c["chunk_id"] for c in resp.json()["results"]]
    assert ids == ["chunk-1a", "chunk-1b", "chunk-1c"]


def test_list_collections(client) -> None:
    resp = client.get("/api/v1/collections")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["collections"]]
    assert names == ["documents"]


def test_openapi_available(client) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/search" in resp.json()["paths"]
