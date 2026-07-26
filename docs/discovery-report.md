# Discovery report

> **Status: TEMPLATE — fill this in against your real environment before
> finalising configuration.** No production retrieval should be relied upon until
> this report is complete. This repository was built without access to the live
> Synology, so every value below is a placeholder to be replaced by the output of
> the read-only discovery scripts.

Run and paste output:

```bash
python scripts/inspect_qdrant.py     >> docs/discovery-report.md
python scripts/inspect_postgres.py   >> docs/discovery-report.md
```

Then translate the findings into `.env` and `config/schema_mapping.yaml`.

---

## 1. Current architecture

- Source files: _Synology share(s): _______
- Vector store: **Qdrant** at `______:6333`
- Metadata store: **PostgreSQL** at `______:5432`, database `______`
- Indexer: **Mac mini** pipeline (unchanged by this project)

## 2. Indexing application and versions

- Indexer app / version: ______
- Qdrant server version: ______
- Embedding provider/library: ______

## 3. Qdrant collection inventory

| Collection | Points | Vector name(s) | Dimensions | Distance |
|---|---|---|---|---|
| `______` | ______ | (unnamed) / `______` | ______ | Cosine / Dot / Euclid |

## 4. Vector dimensions and distance metric

- Dimensions: ______ → set `EMBEDDING_DIMENSIONS`
- Distance: ______ (informational; must match how vectors were built)
- Query vector normalisation required? ______ → set `EMBEDDING_NORMALISE`

## 5. Payload samples (confidential content redacted)

Paste `inspect_qdrant.py` sample output here (values are truncated/redacted by
the script). Identify the key for each domain field:

| Domain field | Payload key |
|---|---|
| text | `______` |
| document_id | `______` |
| chunk_id | `______` (or point id) |
| filename | `______` |
| title | `______` |
| page_number | `______` |
| slide_number | `______` |
| sheet_name | `______` |
| section | `______` |
| file_type | `______` |
| source_uri | `______` (only if safe/opaque) |
| modified_at | `______` |
| created_at | `______` |
| folder | `______` |
| **sequence** (neighbour order) | `______` |
| active/latest flag | `______` (or none) |

## 6. PostgreSQL schema inventory

Paste `inspect_postgres.py` output. Prefer an approved **view** exposing only
client-safe columns.

- Metadata table/view: `______`
- Document id column: `______`
- Column → domain-field mapping: ______

## 7. Document-to-chunk relationships

- How chunks relate to documents: ______
- How chunk ordering is represented (the field used for neighbours): ______

## 8. Embedding provider and model

- Model: `______` → set `EMBEDDING_MODEL`
- Endpoint (OpenAI-compatible base URL): `______` → set `EMBEDDING_BASE_URL`
- Compatibility confirmed by: startup dimension check + a smoke query

## 9. Metadata completeness assessment

- Is all citation metadata in Qdrant payloads? ______
- If not, which fields require PostgreSQL enrichment? ______ → set
  `metadata_source: both` (or `postgres`) for the affected collection(s).

## 10. Citation feasibility

- Can we form a stable display name + locator per document? ______
- Is a safe `source_uri` available (no raw UNC/absolute path)? ______

## 11. Known stale, duplicate, or deleted records

- Are superseded/deleted documents retained in the index? ______
- Is there a reliable active/latest flag? ______ (maps to `active_flag`)

## 12. Security observations

- Can Qdrant issue a restricted read-only credential? ______
- Is the reader PostgreSQL account SELECT-only? ______
- Are Qdrant/PostgreSQL ports blocked from the internet? ______

## 13. Recommended Phase 1 mapping

Summarise the concrete `.env` values and `config/schema_mapping.yaml` you will
commit (to the ignored real file, not the example).

## 14. Open issues and assumptions

- ______

---

### Exit criteria (Phase 0)

- [ ] Existing schema understood and mapped.
- [ ] Embedding model + dimensions confirmed and set.
- [ ] No unresolved question prevents safe read-only retrieval.
- [ ] Required credentials and network access available.
