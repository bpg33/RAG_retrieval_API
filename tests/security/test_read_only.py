"""Security tests: read-only enforcement at the application layer."""

from __future__ import annotations

import pytest

from synology_rag.adapters.postgres_repository import PostgresRepository
from synology_rag.adapters.qdrant_repository import QdrantRepository
from synology_rag.config import PostgresCollectionMapping

pytestmark = pytest.mark.security

_WRITE_METHOD_MARKERS = (
    "upsert",
    "set_payload",
    "overwrite",
    "clear_payload",
    "delete_vectors",
    "create_collection",
    "delete_collection",
    "recreate",
    "insert",
)


def test_qdrant_repository_has_no_write_methods() -> None:
    names = {n.lower() for n in dir(QdrantRepository)}
    for marker in _WRITE_METHOD_MARKERS:
        assert not any(marker in n for n in names), f"unexpected {marker} method"


def test_qdrant_repository_exposes_only_reads() -> None:
    public = {n for n in dir(QdrantRepository) if not n.startswith("_")}
    assert public == {
        "search",
        "retrieve",
        "scroll",
        "collection_exists",
        "collection_stats",
        "from_settings",
        "aclose",
    }


def test_postgres_repository_has_no_write_methods() -> None:
    names = {n.lower() for n in dir(PostgresRepository)}
    for marker in _WRITE_METHOD_MARKERS:
        assert not any(marker in n for n in names)


def test_postgres_select_is_parameterised() -> None:
    pgm = PostgresCollectionMapping(
        schema="public",
        table="docs_v",
        document_id_column="document_id",
        columns={"filename": "filename", "title": "title"},
    )
    rendered = PostgresRepository._build_select(pgm).as_string(None)
    assert rendered.startswith("SELECT")
    assert "= ANY(%s)" in rendered  # values are bound, never concatenated
    assert '"public"."docs_v"' in rendered
    for keyword in ("INSERT", "UPDATE", "DELETE", "DROP"):
        assert keyword not in rendered


def test_source_scan_finds_no_writes() -> None:
    # Mirror the verify_read_only source scan on the installed package.
    import re
    from pathlib import Path

    import synology_rag

    src = Path(synology_rag.__file__).resolve().parent
    forbidden = [
        re.compile(r"\.upsert\("),
        re.compile(r"\.set_payload\("),
        re.compile(r"\bcreate_collection\("),
        re.compile(r"\bdelete_collection\("),
    ]
    sql_write = re.compile(
        r"\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|DROP\s+(TABLE|VIEW))\b"
    )
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert not pattern.search(text), f"{path}: {pattern.pattern}"
        assert not sql_write.search(text), f"{path}: SQL write"
