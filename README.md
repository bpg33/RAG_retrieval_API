# Synology RAG Retrieval Platform

A **read-only** Retrieval-Augmented Generation platform over an **existing**
Synology-hosted Qdrant + PostgreSQL document index. One shared, protocol-
independent retrieval engine is exposed through a local **REST API** and a local
**MCP** adapter, so Claude, a local ChatGPT-style app, or any other client can
search your indexed documents and get cited passages.

```
   MCP client ─┐
               ├─▶  Retrieval engine  ─▶  Qdrant (vectors)  ┐
   REST client ┘     (validation,          PostgreSQL (meta) ├─ Synology NAS
                      filtering, dedup,                       ┘
                      neighbours, ranking,
                      citations)
```

> ⚠️ **Security posture.** This service is read-only by design and binds to
> `127.0.0.1` by default. It never re-indexes, writes, deletes, or modifies your
> documents, Qdrant collections, or PostgreSQL data. Read-only is enforced in
> code, credentials, and network rules — not by a prompt. See
> [`docs/security.md`](docs/security.md).

## What it does (and does not)

**In scope (Phase 1):** dense vector search over your existing collections,
approved metadata filters, neighbour-chunk expansion, deduplication, stable
citations, a local REST API, and a local MCP server — all read-only.

**Out of scope:** indexing, parsing, embedding generation for documents, writing
to Qdrant/PostgreSQL/Synology, arbitrary SQL, arbitrary filesystem access, remote
internet access, multi-user administration, and hybrid/reranking retrieval
(explicitly deferred). The Mac mini indexing pipeline is left untouched.

## Architecture in one paragraph

The **retrieval engine** (`src/synology_rag/retrieval/`) owns all business logic
and depends only on abstract ports (`domain/ports.py`). The **adapters**
(`adapters/`) are read-only implementations for Qdrant, PostgreSQL, and
embeddings. The **REST** (`api/`) and **MCP** (`mcp/`) layers are thin
translators that call the same engine, guaranteeing equivalent results. The shape
of your *existing* index is described entirely in a
[schema-mapping YAML](config/schema_mapping.example.yaml) plus environment
variables — there are no hardcoded payload keys. Full detail:
[`docs/architecture.md`](docs/architecture.md).

## Quick start

```bash
# 1. Install (Python 3.11+; 3.12 recommended)
uv venv .venv && VIRTUAL_ENV=.venv uv pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
cp config/schema_mapping.example.yaml config/schema_mapping.yaml
#    Fill both in from your discovery report (see below).

# 3. Discover your existing index (read-only)
python scripts/inspect_qdrant.py     >> docs/discovery-report.md
python scripts/inspect_postgres.py   >> docs/discovery-report.md

# 4. Verify read-only enforcement
python scripts/verify_read_only.py

# 5. Smoke test end-to-end
python scripts/smoke_test.py --query "your question here"

# 6. Run the REST API (http://127.0.0.1:8765/docs)
python -m synology_rag.api

# 7. Or run the MCP server (stdio)
python -m synology_rag.mcp.server
```

On Windows without `make`, use `scripts/install-windows.ps1` (see
[`docs/deployment-windows.md`](docs/deployment-windows.md)).

## Discovery first

Before finalising configuration, run the read-only discovery scripts against your
environment and record findings in
[`docs/discovery-report.md`](docs/discovery-report.md): embedding model and
dimensions, distance metric, collection and vector names, payload keys, PostgreSQL
tables/columns, chunk/document identifiers, neighbour ordering, and version/stale
handling. Those findings become entries in `.env` and
`config/schema_mapping.yaml` — **not** code changes.

## Configuration

- `.env` — connection details, secrets, and limits. See
  [`.env.example`](.env.example).
- `config/schema_mapping.yaml` — how public fields map to your discovered Qdrant
  payload keys and PostgreSQL columns. See
  [`config/schema_mapping.example.yaml`](config/schema_mapping.example.yaml).

Startup **fails closed** on missing/invalid configuration (bad dimensions, no
allowed collection, non-local bind without acknowledgement, missing embedding
model, unmapped collections, schema mismatch).

## Tests, lint, types

```bash
make test        # unit + contract + security + retrieval-quality (no live services)
make test-int    # integration tests (needs live services + RUN_INTEGRATION=1)
make lint        # ruff
make typecheck   # mypy (strict)
make verify-readonly
make benchmark   # retrieval quality + latency report
```

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Components, boundaries, pipeline |
| [`docs/discovery-report.md`](docs/discovery-report.md) | Existing-index mapping (fill in) |
| [`docs/security.md`](docs/security.md) | Threat model, permissions, residual risks |
| [`docs/api.md`](docs/api.md) | REST endpoints and examples |
| [`docs/mcp-tools.md`](docs/mcp-tools.md) | MCP tools, schemas, client setup |
| [`docs/deployment-windows.md`](docs/deployment-windows.md) | Native + Docker on Windows |
| [`docs/deployment-synology-future.md`](docs/deployment-synology-future.md) | Future Synology-hosted proxy |
| [`docs/retrieval-evaluation.md`](docs/retrieval-evaluation.md) | Benchmark methodology + results |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Connectivity, mismatches, performance |
| [`docs/rollback-checklist.md`](docs/rollback-checklist.md) | Deployment + rollback |

## License

Proprietary. Not for redistribution.
