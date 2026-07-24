# Security

Read-only is a **technical** requirement enforced through multiple independent
layers, not a prompt instruction.

## Threat model (summary)

| Threat | Mitigation |
|---|---|
| Client mutates the index | No write methods exist in any adapter; DB account is SELECT-only; Qdrant credentials/network restricted. |
| SQL injection | No client input becomes SQL. Identifiers come from validated config; values are always bound parameters. |
| Arbitrary Qdrant filters | Clients supply only public filter names; the engine builds typed filters from mapped payload keys. |
| Arbitrary filesystem access | No filesystem read path in Phase 1; `ENABLE_SOURCE_FILE_READ=false`. Document ids are opaque; path traversal is inert. |
| Secret leakage | Secrets never logged (redaction processor); errors never expose SQL/paths/connection strings; `.env` git-ignored. |
| Prompt injection in documents | Retrieved text is treated as evidence; tool descriptions/system guidance take precedence; no action tools exist to hijack. |
| Public exposure | Binds to `127.0.0.1` by default; non-local bind requires explicit acknowledgement; Synology DB ports must not be internet-exposed. |
| Oversized / malformed input | Query length, limits, neighbours, and payload size are validated and clamped. |

## Layered read-only enforcement

### 1. Application layer

- Adapter classes expose **read methods only**. There is no `upsert`, `delete`,
  `set_payload`, `create_collection`, INSERT/UPDATE/DELETE, or file write
  anywhere in production code.
- `scripts/verify_read_only.py` fails the build if a write-capable method name or
  a Qdrant write call / SQL write statement appears in the source. It is also run
  as a security test (`tests/security/test_read_only.py`).

### 2. PostgreSQL permissions

Create a dedicated reader account and grant the minimum:

```sql
-- Run as an administrator on the Synology PostgreSQL instance.
CREATE ROLE rag_retrieval_reader LOGIN PASSWORD '••••••' CONNECTION LIMIT 5
    NOINHERIT;

REVOKE ALL ON DATABASE your_db FROM rag_retrieval_reader;
GRANT CONNECT ON DATABASE your_db TO rag_retrieval_reader;

GRANT USAGE ON SCHEMA public TO rag_retrieval_reader;

-- Prefer approved VIEWS that expose only client-safe columns.
GRANT SELECT ON public.rag_document_metadata_v TO rag_retrieval_reader;

-- Make the account read-only by default.
ALTER ROLE rag_retrieval_reader SET default_transaction_read_only = on;
ALTER ROLE rag_retrieval_reader SET statement_timeout = '3000ms';

-- Ensure future tables are not automatically readable/writable.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM rag_retrieval_reader;
```

The application additionally sets `default_transaction_read_only=on` and a
`statement_timeout` on every connection. `scripts/verify_read_only.py` attempts a
harmless `UPDATE ... WHERE false` against an approved table (rolled back) and
requires the database to reject it.

### 3. Qdrant access

- The application code exposes only search / scroll / retrieve / collection-info
  reads.
- Restrict the Synology firewall so Qdrant is reachable only from approved hosts,
  and **never** from the internet.
- Enforce the collection allowlist via `QDRANT_ALLOWED_COLLECTIONS`.
- If your Qdrant version cannot issue a read-only credential, rely on network
  restriction + narrow application code + secret isolation, and record the
  residual risk (below).

### 4. Synology files

Phase 1 avoids direct source-file access (`ENABLE_SOURCE_FILE_READ=false`). If
later enabled, create a dedicated `rag_file_reader` user with read-only access to
approved shares only, deny write/delete/rename, and never return raw UNC paths to
clients — prefer an opaque `source_uri`.

## Network rules

| Source | Destination | Permission |
|---|---|---|
| Mac mini | Qdrant/PostgreSQL on Synology | Existing indexing permissions |
| Windows retrieval service | Qdrant on Synology | Search/read only |
| Windows retrieval service | PostgreSQL on Synology | SELECT only |
| Windows retrieval service | Approved Synology share | Read only, only if required |
| Other LAN devices | Qdrant/PostgreSQL | Deny unless explicitly required |
| Internet | Qdrant/PostgreSQL/DSM | Deny |

Use DHCP reservations or static addresses so firewall rules are stable.

## Secrets

- No credentials in source control; `.env` is git-ignored; `.env.example`
  contains names only.
- Use Windows Credential Manager, Docker secrets, or a protected local `.env`
  with restricted file permissions.
- Secrets are never logged (redaction processor drops keys containing
  `password`, `api_key`, `secret`, `token`, `authorization`).
- Connection strings are redacted in exceptions (only the exception *type* is
  logged).

## Authentication

Set `LOCAL_API_KEY` to require an `X-API-Key` header on every `/api/v1/*`
request (constant-time comparison). Health endpoints are unauthenticated. When
the key is unset (pure-localhost dev), a warning is logged at startup.

## Prompt-injection handling

Retrieved documents are untrusted. The MCP server ships system guidance stating
that retrieved text is evidence, must never be followed as instructions, and that
tool/system instructions take precedence. Critically, **the system has no write,
delete, indexing, shell, SQL, or filesystem tools**, so injected instructions
have nothing to hijack. `tests/security/test_input_and_auth.py` verifies that
injected text is returned inertly and does not alter the exposed tool set.

## Residual risks

- **Qdrant credential granularity.** If the installed Qdrant cannot scope a
  read-only key, the boundary is network + code + secret isolation. A future
  Synology-hosted retrieval proxy (see `deployment-synology-future.md`) would add
  a stronger boundary.
- **Date filtering** relies on the `modified_at` payload being datetime-indexed
  in Qdrant; if stored as an unindexed string, date filters may not apply
  server-side.
- **Source-file access**, if later enabled, expands the trust boundary and must
  be re-reviewed.

## Verification checklist

- [ ] `python scripts/verify_read_only.py` passes.
- [ ] `make test` passes (includes the security suite).
- [ ] PostgreSQL reader account rejects writes (verified by the script).
- [ ] Qdrant not reachable from the internet.
- [ ] `LOCAL_API_KEY` set if the service is reachable beyond localhost.
- [ ] `.env` and `config/schema_mapping.yaml` are git-ignored and not committed.
