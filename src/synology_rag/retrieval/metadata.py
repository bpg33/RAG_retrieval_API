"""Map Qdrant payloads to chunks and enrich them from PostgreSQL.

``chunk_from_hit`` builds a :class:`RetrievedChunk` using only the collection's
schema mapping - no payload key is assumed. ``enrich_candidates`` fills missing
citation fields from approved PostgreSQL views in a single batched query per
collection (never one query per chunk).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from synology_rag.config import CollectionMapping, MetadataSource, PayloadMapping, SchemaMapping
from synology_rag.domain.models import RetrievedChunk
from synology_rag.domain.ports import MetadataRepository, VectorHit
from synology_rag.retrieval.candidate import Candidate

# Fields that PostgreSQL enrichment is allowed to populate on a chunk.
_ENRICHABLE = (
    "text",
    "filename",
    "title",
    "file_type",
    "source_uri",
    "modified_at",
    "page_number",
    "slide_number",
    "sheet_name",
    "section",
)


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def _get(payload: dict[str, Any], key: str | None) -> Any:
    if key is None:
        return None
    return payload.get(key)


def chunk_from_hit(hit: VectorHit, coll: CollectionMapping) -> Candidate:
    """Build a candidate chunk from a Qdrant hit using the collection mapping."""
    p: PayloadMapping = coll.payload
    payload = hit.payload

    chunk_id = _coerce_str(_get(payload, p.chunk_id)) or hit.id
    document_id = _coerce_str(_get(payload, p.document_id)) or chunk_id
    text = _coerce_str(_get(payload, p.text)) or ""
    sequence = _coerce_int(_get(payload, p.sequence))

    chunk = RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        score=hit.score,
        rank=0,
        collection=hit.collection,
        filename=_coerce_str(_get(payload, p.filename)),
        title=_coerce_str(_get(payload, p.title)),
        page_number=_coerce_int(_get(payload, p.page_number)),
        slide_number=_coerce_int(_get(payload, p.slide_number)),
        sheet_name=_coerce_str(_get(payload, p.sheet_name)),
        section=_coerce_str(_get(payload, p.section)),
        file_type=_coerce_str(_get(payload, p.file_type)),
        source_uri=_coerce_str(_get(payload, p.source_uri)),
        modified_at=_coerce_datetime(_get(payload, p.modified_at)),
    )
    if coll.source_uri is not None:
        chunk.source_uri = _build_source_uri(payload, coll, chunk)
    return Candidate(chunk=chunk, sequence=sequence, active=active_flag(payload, coll))


def _build_source_uri(
    payload: dict[str, Any], coll: CollectionMapping, chunk: RetrievedChunk
) -> str | None:
    """Reconstruct a client-openable URI from a stored path via the template."""
    template = coll.source_uri
    if template is None:
        return None
    raw = _coerce_str(payload.get(template.from_payload))
    if not raw:
        return None
    path = raw
    if template.strip_prefix and path.startswith(template.strip_prefix):
        path = path[len(template.strip_prefix) :]
    if template.separator is not None:
        path = path.replace("/", template.separator)
    uri = f"{template.add_prefix}{path}"
    if (
        template.pdf_page_anchor
        and (chunk.file_type or "").lower() == "pdf"
        and chunk.page_number is not None
    ):
        uri += f"#page={chunk.page_number}"
    return uri


def chunk_from_row(row: dict[str, Any], collection: str) -> Candidate:
    """Build a candidate from a PostgreSQL neighbour row (domain-field dict)."""
    chunk = RetrievedChunk(
        chunk_id=_coerce_str(row.get("chunk_id")) or "",
        document_id=_coerce_str(row.get("document_id")) or "",
        text=_coerce_str(row.get("text")) or "",
        score=0.0,
        rank=0,
        collection=collection,
        filename=_coerce_str(row.get("filename")),
        title=_coerce_str(row.get("title")),
        page_number=_coerce_int(row.get("page_number")),
        slide_number=_coerce_int(row.get("slide_number")),
        sheet_name=_coerce_str(row.get("sheet_name")),
        section=_coerce_str(row.get("section")),
        file_type=_coerce_str(row.get("file_type")),
        modified_at=_coerce_datetime(row.get("modified_at")),
    )
    return Candidate(chunk=chunk, sequence=_coerce_int(row.get("sequence")))


def active_flag(payload: dict[str, Any], coll: CollectionMapping) -> bool | None:
    """Return the latest/active-version flag if the collection maps one."""
    key = coll.payload.active_flag
    if key is None:
        return None
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y", "latest", "active")
    if isinstance(value, (int, float)):
        return bool(value)
    return None


async def enrich_candidates(
    candidates: list[Candidate],
    mapping: SchemaMapping,
    repo: MetadataRepository | None,
) -> tuple[list[Candidate], list[str]]:
    """Hydrate candidates from PostgreSQL and enforce liveness.

    Fills missing fields (including chunk text) from the approved view, keyed per
    the collection's ``lookup_key``. When ``drop_if_missing`` is set, a candidate
    whose row is absent is dropped - this is how liveness works when the view
    already excludes removed/superseded rows. Returns ``(kept, warnings)``.
    """
    warnings: list[str] = []
    if not candidates:
        return candidates, warnings

    by_collection: dict[str, list[Candidate]] = {}
    for cand in candidates:
        coll = mapping.for_collection(cand.chunk.collection)
        if coll.metadata_source is MetadataSource.QDRANT:
            continue
        by_collection.setdefault(cand.chunk.collection, []).append(cand)

    if not by_collection:
        return candidates, warnings

    if repo is None:
        warnings.append("Metadata database is not configured; returning Qdrant metadata only.")
        return candidates, warnings

    drop: set[int] = set()
    for collection, cands in by_collection.items():
        coll = mapping.for_collection(collection)
        pgm = coll.postgres
        if pgm is None:  # pragma: no cover - guarded by config validation
            continue
        use_chunk = pgm.lookup_key == "chunk_id"

        def key_of(cand: Candidate, *, use_chunk: bool = use_chunk) -> str:
            return cand.chunk.chunk_id if use_chunk else cand.chunk.document_id

        keys = sorted({key_of(c) for c in cands})
        try:
            rows = await repo.fetch_metadata(collection=collection, keys=keys)
        except Exception:  # PostgresUnavailableError etc.; degrade gracefully
            warnings.append(
                f"Metadata enrichment for collection '{collection}' is temporarily "
                "unavailable; returning Qdrant metadata only."
            )
            continue
        for cand in cands:
            fields = rows.get(key_of(cand))
            if fields is None:
                if pgm.drop_if_missing:
                    drop.add(id(cand))
                continue
            _apply_pg_fields(cand.chunk, fields)
            if cand.sequence is None and "sequence" in fields:
                cand.sequence = _coerce_int(fields["sequence"])

    if not drop:
        return candidates, warnings
    kept = [c for c in candidates if id(c) not in drop]
    if len(kept) < len(candidates):
        warnings.append(
            f"{len(candidates) - len(kept)} result(s) omitted: no longer present in the index."
        )
    return kept, warnings


_INT_FIELDS = frozenset({"page_number", "slide_number"})
_DATETIME_FIELDS = frozenset({"modified_at"})


def _apply_pg_fields(chunk: RetrievedChunk, fields: dict[str, Any]) -> None:
    """Fill only fields currently missing on the chunk (fill-the-gaps)."""
    for field in _ENRICHABLE:
        if field not in fields:
            continue
        if field == "text":
            if not chunk.text:
                chunk.text = _coerce_str(fields["text"]) or ""
            continue
        if getattr(chunk, field) is not None:
            continue
        if field in _INT_FIELDS:
            value: Any = _coerce_int(fields[field])
        elif field in _DATETIME_FIELDS:
            value = _coerce_datetime(fields[field])
        else:
            value = _coerce_str(fields[field])
        setattr(chunk, field, value)
