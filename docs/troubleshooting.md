# Troubleshooting

## Startup fails immediately

Startup **fails closed** on configuration problems. The error message names the
cause. Common ones:

| Message contains | Fix |
|---|---|
| `EMBEDDING_MODEL is required` / `EMBEDDING_DIMENSIONS is required` | Set both in `.env` (from discovery), or use `EMBEDDING_PROVIDER=fake` for offline dev. |
| `QDRANT_ALLOWED_COLLECTIONS must list at least one collection` | Set the allowlist. |
| `Allowed collections without a schema mapping` | Add each collection to `config/schema_mapping.yaml`. |
| `BIND_HOST=… is non-local` | Keep `127.0.0.1`, or set `ALLOW_NON_LOCAL_BIND=true` deliberately. |
| `needs PostgreSQL … but POSTGRES_ENABLED=false` | Set `POSTGRES_ENABLED=true` (and DB creds) or change the collection's `metadata_source` to `qdrant`. |
| `Configured collection … does not exist` | Fix the collection name, or run against the right Qdrant. Disable `STARTUP_VERIFY_COLLECTIONS` only for offline dev. |
| `vector size … does not match EMBEDDING_DIMENSIONS` | Your embedding dimensions differ from the index. Do **not** change the model silently — re-check discovery. |

## Connectivity

- **Ping works but the port is refused** (`TcpTestSucceeded: False`): the host is
  up but the service isn't listening on that interface. Commonly the DB/vector
  containers are published to `127.0.0.1` only, or are on a *different host* than
  you assumed (e.g. the index runs on the Mac mini, not the Synology). Point
  `QDRANT_URL`/`POSTGRES_HOST` at the host that actually runs them, publish the
  container ports to the LAN (`0.0.0.0:PORT` or `<host-ip>:PORT`), and allow the
  desktop's IP through that host's firewall. If embeddings come from Ollama, it
  must also listen on the LAN (`OLLAMA_HOST=0.0.0.0`).
- **Qdrant unreachable** (`qdrant_unavailable`): verify `QDRANT_URL` and that the
  host firewall allows the desktop's IP to the Qdrant port. Test:
  `curl http://<host>:6333/collections`.
- **PostgreSQL unreachable** (`postgres_unavailable`): check host/port/SSL and the
  reader account. Test with `psql` using the reader credentials.
- **From Docker**, `localhost` means the container. Use the Synology's LAN address
  and, if needed, an `extra_hosts` entry.
- **One of several collections is down:** by default the search fails. Set
  `PARTIAL_RESULTS_ON_COLLECTION_ERROR=true` to return results from the reachable
  collections with a warning instead (it still fails if *all* are unavailable).

## Embedding mismatch

- `embedding_incompatible`: the endpoint returned a vector of the wrong size.
  Confirm `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` match the indexing model
  exactly. Different providers/models are not interchangeable.
- `embedding_unavailable`: the endpoint is down or rejected credentials. Check
  `EMBEDDING_BASE_URL`/`EMBEDDING_API_KEY`. `/health/ready` reports embedding
  status.

## Empty results

- The query genuinely has no support in the index — the response says the evidence
  is insufficient. Trust it rather than lowering the bar blindly.
- A `minimum_score` (request or `DEFAULT_MINIMUM_SCORE`) may be too high.
- Filters removed everything — check `file_types`, `folders`, `metadata_filters`,
  and the date range. A `warnings` entry usually explains this.
- Wrong collection — confirm `collections` / `QDRANT_ALLOWED_COLLECTIONS`.

## Metadata / citation issues

- Missing filename/title/locator: confirm the payload keys in
  `config/schema_mapping.yaml`, or enable PostgreSQL enrichment
  (`metadata_source: both`).
- Neighbours missing: the `sequence` payload key must be mapped and numeric.
  Lexical chunk-id order is never assumed.
- Wrong locator: check `page_number` / `slide_number` / `sheet_name` / `section`
  mappings.

## Permission errors

- `verify_read_only.py` reports the reader account can write: tighten the grants
  (see `docs/security.md`). The account must be SELECT-only.
- `authentication_failed` on REST: send `X-API-Key` matching `LOCAL_API_KEY`.

## Performance

- Use `/metrics` and the benchmark report to find the slow stage.
- Large `MAX_RETURNED_CHARACTERS` or high `limit`/neighbours increase latency and
  payload size.
- Slow Qdrant: check network latency to the Synology and consider `QDRANT_PREFER_GRPC=true`.
- Slow embeddings often dominate — a local embedding server on the LAN reduces
  round trips.
- Tune `QDRANT_TIMEOUT_SECONDS`, `POSTGRES_STATEMENT_TIMEOUT_MS`,
  `SEARCH_TIMEOUT_SECONDS` to your environment.

## Logs

- Structured JSON on stderr. Query **text** is not logged unless
  `LOG_CONTENT=true` (development only).
- Every REST response has an `X-Request-ID`; grep logs for it to trace a request.
