# Architecture

## Goals

- One tested retrieval engine, reused by REST and MCP with no duplicated logic.
- Read-only at every layer (code, credentials, network).
- The shape of the *existing* index is configuration, not code.
- Fully unit-testable without live Qdrant/PostgreSQL/embedding services.

## Layered design

```
+--------------------------------------------------------------+
|  Adapters (protocol edges)                                   |
|   api/   FastAPI REST      mcp/   FastMCP tools              |
|      \                        /                              |
|       \        both call     /                               |
|        v                    v                                |
|  retrieval/  RetrievalService  (the engine)                  |
|    validation → normalisation → embedding → filters →        |
|    vector search → metadata enrichment → dedup →             |
|    neighbours → ranking → context budget → citations         |
|        |            depends only on ports (interfaces)       |
|        v                                                     |
|  domain/ports.py   EmbeddingProvider | VectorRepository |    |
|                    MetadataRepository                        |
|        ^                                                     |
|        |  implemented by                                     |
|  adapters/  QdrantRepository | PostgresRepository |          |
|             OpenAICompatible/Fake EmbeddingProvider          |
+--------------------------------------------------------------+
                     |                     |
              Qdrant (read)         PostgreSQL (SELECT)
                     \                     /
                      +---- Synology NAS -+
```

### Dependency rule

`domain/` and `retrieval/` never import FastAPI, MCP, Qdrant, or psycopg. The
engine is written against `domain/ports.py` protocols and returns
`domain/models.py` dataclasses. This is what lets the same engine serve two
protocols and be tested with in-memory fakes (`tests/fakes.py`).

## Components

| Package | Responsibility |
|---|---|
| `config.py` | Typed settings (env) + schema-mapping (YAML). Fails closed. Validates SQL identifiers. |
| `domain/models.py` | `SearchRequest`, `RetrievedChunk`, `Citation`, `SearchResponse`, `DocumentMetadata`, `CollectionInfo`. |
| `domain/errors.py` | Typed errors with stable codes + HTTP status + retryability. |
| `domain/ports.py` | `EmbeddingProvider`, `VectorRepository`, `MetadataRepository` protocols + transfer types. |
| `retrieval/` | The engine: one module per pipeline stage + `service.py` orchestrator. |
| `adapters/qdrant_repository.py` | Read-only Qdrant: search / retrieve / scroll / collection info. |
| `adapters/postgres_repository.py` | Read-only, parameterised SELECT metadata enrichment. |
| `adapters/embedding_provider.py` | OpenAI-compatible + deterministic fake providers. |
| `api/` | FastAPI app, routes, schemas, auth, error mapping. |
| `mcp/` | FastMCP server exposing four read-only tools. |
| `observability/` | Structured logging (redacted), metrics, audit log. |
| `container.py` | Composition root; wires adapters and owns lifecycle. |

## Retrieval pipeline (stages)

1. **Validate** (`validation.py`) — trim/clamp, reject empty/oversized/invalid
   Unicode, resolve the collection allowlist, reject unsupported filters and
   malformed date ranges. Produces a trusted `ValidatedRequest`.
2. **Normalise** (`query_normalisation.py`) — conservative whitespace only; no
   LLM expansion in Phase 1.
3. **Embed** (`embeddings.py` + provider) — same model/dimensions as the index;
   fails closed on incompatibility.
4. **Filter** (`filters.py`) — build a typed `QueryFilter` from validated inputs
   and *mapped* payload keys only.
5. **Vector search** (`service.py` + `QdrantRepository`) — per approved
   collection, oversampled candidate set, optional score threshold.
6. **Map + enrich** (`metadata.py`) — payload → `RetrievedChunk` via the schema
   mapping; batched PostgreSQL enrichment when configured.
7. **Deduplicate** (`deduplication.py`) — exact ids, identical text, contained
   overlaps within a document, superseded versions (when a flag is mapped).
8. **Rank** (`ranking.py`) — vector similarity first, active-version preference
   as a tie-breaker.
9. **Neighbours** (`neighbours.py`) — adjacent chunks by explicit sequence
   metadata only; marked, de-duplicated, never displacing primaries.
10. **Context budget** (`context_budget.py`) — cap total chunks, per-chunk chars,
    and total chars; truncation is explicit.
11. **Citations** (`citations.py`) — one stable citation per document with a
    page/slide/sheet/section locator.

## Configuration-driven schema mapping

The single most important design decision: **the engine reads nothing about
payload structure from constants.** `config/schema_mapping.yaml` maps public
fields to your discovered Qdrant payload keys and PostgreSQL columns, per
collection, including the neighbour-ordering `sequence` key and optional
active-version flag. Discovery findings translate directly into this file, so new
indexes or schema changes are configuration, not code changes.

## Error handling

Typed `RetrievalError` subclasses carry a stable `code`, safe `message`,
`http_status`, and `retryable`. The REST layer maps them to structured JSON; the
MCP layer returns them as structured `error` payloads. Internal detail (for logs)
is never returned to clients.

## Observability

Structured JSON logs with secret redaction; query **length** is logged, not text
(unless `LOG_CONTENT=true`). In-process metrics counters/latencies are exposed at
`/metrics`. A privacy-conscious audit log records who searched, when, which
collections, and which document ids were returned — never passage text.
