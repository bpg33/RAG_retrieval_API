# Deployment and rollback checklist

This service is read-only and stateless: it holds no data of its own, so
"rollback" means reverting configuration/version and stopping the process. The
existing index and the Mac mini pipeline are never modified by this service.

## Pre-deployment

- [ ] Discovery report complete (`docs/discovery-report.md`).
- [ ] `.env` and `config/schema_mapping.yaml` filled in and **not** committed.
- [ ] `python scripts/verify_read_only.py` passes.
- [ ] `make test` passes (unit, contract, security, retrieval-quality).
- [ ] `make lint` and `make typecheck` pass.
- [ ] PostgreSQL reader account is SELECT-only (verified by the script).
- [ ] Qdrant/PostgreSQL not reachable from the internet.
- [ ] `LOCAL_API_KEY` set if the service is reachable beyond localhost.
- [ ] Real benchmark baseline recorded (`docs/retrieval-evaluation.md`).

## Deploy

- [ ] Note the current version/commit (for rollback).
- [ ] Start the service (native: `python -m synology_rag.api`, or `docker compose up`).
- [ ] `GET /health/live` returns 200.
- [ ] `GET /health/ready` returns 200 with expected dependency status.
- [ ] Smoke test: `python scripts/smoke_test.py --query "…"` returns cited results.
- [ ] REST and MCP both return results for a known query.

## Post-deploy verification

- [ ] `/metrics` shows searches succeeding, low error rate.
- [ ] Logs are structured and contain no query text (unless intentionally enabled).
- [ ] Spot-check citations against source documents.

## Rollback

Because the service is read-only and stateless, rollback is low-risk:

1. [ ] Stop the service (Ctrl+C / `docker compose down` / stop the Windows service).
2. [ ] Revert to the previous version/commit and/or restore the previous `.env`
       and `config/schema_mapping.yaml`.
3. [ ] Restart and re-run the health + smoke checks above.
4. [ ] If the problem was a schema/embedding mismatch, re-open discovery — do not
       change the embedding model silently.

## What rollback never requires

- No data migration or restore (the service owns no data).
- No changes to Qdrant, PostgreSQL, or Synology files.
- No changes to the Mac mini indexing pipeline.

## Incident notes

- Dependency outage (Qdrant/PostgreSQL/embeddings) surfaces as a `*_unavailable`
  error with `retryable: true`; the service recovers when the dependency does.
- Configuration errors fail closed at startup with a specific message — fix and
  restart.
