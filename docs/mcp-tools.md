# MCP tools

The MCP server exposes the same retrieval engine as the REST API over a **local
stdio** transport. No LAN port is opened. Run it with:

```bash
python -m synology_rag.mcp.server
```

Only four **read-only** tools are exposed. Write, delete, indexing, shell, SQL,
and filesystem tools are intentionally absent (verified by
`tests/security` and `tests/contract`).

## Tools

### `search_documents`

Search approved collections and return relevant passages with citations.

Input:

```json
{
  "query": "string (required)",
  "limit": 10,
  "collections": ["string"],
  "folders": ["string"],
  "file_types": ["string"],
  "date_from": "ISO-8601 date-time or null",
  "date_to": "ISO-8601 date-time or null",
  "include_neighbours": true
}
```

Output (bounded): `query`, `search_id`, `result_count`, `elapsed_ms`,
`truncated`, `warnings`, `results[]` (each with `rank`, `text`, `source`,
`locator`, `document_id`, `chunk_id`, `score`, `is_neighbour`, `citation`), and
`citations[]`. It warns when evidence is weak or filters removed all results.

### `get_document_metadata`

```json
{ "document_id": "string" }
```

Returns approved metadata only (no credentials, connection strings, or sensitive
absolute paths).

### `get_chunk_context`

```json
{ "chunk_id": "string", "neighbours_before": 1, "neighbours_after": 1 }
```

Returns the chunk plus a capped number of neighbouring chunks.

### `list_document_collections`

```json
{}
```

Returns the approved searchable collections and descriptions.

## System guidance shipped to clients

The server advertises guidance instructing the model to treat retrieved passages
as **evidence, not instructions**, to cite the returned filename and locator, to
report insufficient evidence rather than fabricate, to avoid trivially repeated
searches, and to never request write/delete/indexing/shell/SQL/filesystem
operations (which are unavailable).

## Client configuration (Claude Desktop example)

Add to the client's MCP config (adjust the working directory and Python path for
your machine). Keep secrets in the environment, not the args.

```json
{
  "mcpServers": {
    "synology-rag": {
      "command": "python",
      "args": ["-m", "synology_rag.mcp.server"],
      "cwd": "C:\\\\path\\\\to\\\\synology-rag-retrieval",
      "env": {
        "QDRANT_URL": "http://synology.local:6333",
        "QDRANT_ALLOWED_COLLECTIONS": "documents",
        "EMBEDDING_PROVIDER": "openai_compatible",
        "EMBEDDING_MODEL": "text-embedding-3-large",
        "EMBEDDING_DIMENSIONS": "3072",
        "EMBEDDING_BASE_URL": "https://api.openai.com/v1",
        "SCHEMA_MAPPING_FILE": "config\\\\schema_mapping.yaml"
      }
    }
  }
}
```

Using the project virtual environment's interpreter (e.g.
`.venv\\Scripts\\python.exe`) is recommended so dependencies resolve. A packaged
executable can be substituted for `python -m …`.

### Verifying only read-only tools are exposed

```bash
python - <<'PY'
import asyncio
from synology_rag.container import build_container
from synology_rag.mcp.server import build_mcp
mcp = build_mcp(build_container())
print(sorted(t.name for t in asyncio.run(mcp.list_tools())))
PY
# → ['get_chunk_context', 'get_document_metadata', 'list_document_collections', 'search_documents']
```

## Notes

- Responses are bounded by the same context budget as REST
  (`MAX_TOTAL_CHUNKS`, `MAX_RETURNED_CHARACTERS`, `MAX_CHARACTERS_PER_CHUNK`).
- Domain errors are returned as structured `{"error": {code, message, retryable}}`
  payloads so the model receives a clear, safe message.
- Logs go to stderr (stdout is the MCP transport).
