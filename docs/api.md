# REST API

- Base path: `/api/v1`
- JSON only, UTF-8
- Binds to `127.0.0.1` by default
- Interactive docs: `http://127.0.0.1:8765/docs`; schema: `/openapi.json`
  (also committed at [`docs/openapi.json`](openapi.json))
- Auth: set `LOCAL_API_KEY`, then send `X-API-Key: <key>` on `/api/v1/*`
- Every response includes an `X-Request-ID` header
- Request bodies larger than `MAX_REQUEST_BYTES` (default 64 KiB) are rejected
  with `413`
- CORS is disabled by default; set `CORS_ALLOW_ORIGINS` (comma-separated) to
  allow a local browser chat app to call the API

## Errors

All errors share this shape and never include stack traces, SQL, secrets, or
internal paths:

```json
{ "error": { "code": "unknown_collection", "message": "…", "retryable": false, "request_id": "01J…" } }
```

Codes: `invalid_request`, `unsupported_filter`, `unknown_collection`,
`embedding_incompatible`, `embedding_unavailable`, `qdrant_unavailable`,
`postgres_unavailable`, `document_not_found`, `chunk_not_found`,
`retrieval_timeout`, `configuration_error`, `authentication_failed`,
`internal_error`.

## `POST /api/v1/search`

Request (only `query` is required):

```json
{
  "query": "What recurring implementation risks were identified in previous asset-tagging projects?",
  "limit": 10,
  "collections": ["documents"],
  "file_types": ["pdf", "pptx"],
  "folders": ["consulting"],
  "date_from": "2024-01-01T00:00:00Z",
  "date_to": "2025-12-31T23:59:59Z",
  "minimum_score": 0.2,
  "include_neighbours": true,
  "neighbours_before": 1,
  "neighbours_after": 1,
  "metadata_filters": { "file_type": "pdf" }
}
```

Response (abridged):

```json
{
  "query": "What recurring implementation risks…",
  "search_id": "01J…",
  "elapsed_ms": 184,
  "truncated": false,
  "warnings": [],
  "results": [
    {
      "chunk_id": "chunk-123", "document_id": "doc-78",
      "text": "The programme identified…", "score": 0.8731, "rank": 1,
      "collection": "documents", "filename": "Asset Tagging Programme Review.pdf",
      "title": "Asset Tagging Programme Review", "page_number": 8,
      "section": "Implementation risks", "file_type": "pdf",
      "modified_at": "2025-11-14T09:30:00Z",
      "is_neighbour": false, "parent_result_chunk_id": null, "truncated": false,
      "metadata": {}
    }
  ],
  "citations": [
    {
      "citation_id": "src-1", "document_id": "doc-78",
      "chunk_ids": ["chunk-123"],
      "display_name": "Asset Tagging Programme Review.pdf",
      "locator": "Page 8", "modified_at": "2025-11-14T09:30:00Z"
    }
  ]
}
```

Notes:
- `limit`, `neighbours_before/after` default to the configured values when
  omitted, and are clamped to configured maxima (a `warnings` entry is added).
- Unknown request fields are rejected (`422`). Raw SQL/Qdrant filters are not
  accepted.
- `metadata_filters` keys must be public filter names defined in your schema
  mapping; unknown keys return `unsupported_filter` (`400`).

## `GET /api/v1/documents/{document_id}`

Returns approved, client-safe document metadata:

```json
{
  "document_id": "doc-78", "display_name": "Asset Tagging Programme Review.pdf",
  "title": "Asset Tagging Programme Review", "file_type": "pdf",
  "source_uri": null, "modified_at": "2025-11-14T09:30:00Z",
  "created_at": null, "collection": "documents", "metadata": {}
}
```

Never returns database internals, credentials, absolute paths, or file contents.
`404 document_not_found` if unknown.

## `GET /api/v1/chunks/{chunk_id}`

Query params: `neighbours_before` (default 1), `neighbours_after` (default 1),
both clamped to configured maxima. Returns a `SearchResponse` containing the
chunk and its neighbours (with citations).

## `GET /api/v1/collections`

Returns the configured allowlist with user-facing descriptions and vector info:

```json
{ "collections": [ { "name": "documents", "description": "…",
  "vector_dimensions": 1024, "distance": "Cosine", "points_count": 48213 } ] }
```

## Health

- `GET /health/live` — process is up; does not touch dependencies.
- `GET /health/ready` — checks Qdrant, embeddings, and (if enabled) PostgreSQL
  with short timeouts; returns `503` when not ready. Never exposes secrets.

```json
{ "status": "ready", "dependencies": { "qdrant": true, "postgres": null, "embedding": true } }
```

## `GET /metrics`

Local operational counters and latency summaries (no secrets, no content).

## curl example

```bash
curl -sS http://127.0.0.1:8765/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $LOCAL_API_KEY" \
  -d '{"query":"asset tagging implementation risks","limit":5}' | jq
```
