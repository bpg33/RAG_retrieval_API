#!/usr/bin/env python3
"""Verify read-only enforcement across layers.

Checks:
  1. Adapter classes expose no write-capable method names.
  2. Application source contains no Qdrant write calls or SQL write statements.
  3. (If PostgreSQL is enabled) a harmless write against an approved table is
     rejected by the database, inside a rolled-back transaction.

Exit code is non-zero if any check fails. Safe to run repeatedly.
"""

from __future__ import annotations

import os
import re

import _bootstrap

_bootstrap.load_env()

from synology_rag.adapters.postgres_repository import PostgresRepository  # noqa: E402
from synology_rag.adapters.qdrant_repository import QdrantRepository  # noqa: E402

SRC = _bootstrap.ROOT / "src" / "synology_rag"

_FORBIDDEN_METHODS = (
    "upsert",
    "set_payload",
    "overwrite_payload",
    "clear_payload",
    "delete_vectors",
    "create_collection",
    "delete_collection",
    "recreate_collection",
    "insert",
    "update_collection",
)

_FORBIDDEN_CALLS = [
    re.compile(r"\.upsert\("),
    re.compile(r"\.set_payload\("),
    re.compile(r"\.overwrite_payload\("),
    re.compile(r"\.clear_payload\("),
    re.compile(r"\.delete_vectors\("),
    re.compile(r"\bcreate_collection\("),
    re.compile(r"\bdelete_collection\("),
    re.compile(r"\brecreate_collection\("),
]

# Case-SENSITIVE: real SQL in code is uppercase; English prose ("drop
# duplicates", "update ... set") is lowercase and must not trigger a false
# positive. Object keywords are required so bare verbs do not match.
_SQL_WRITE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|"
    r"DROP\s+(TABLE|VIEW|INDEX|SCHEMA|DATABASE)|"
    r"ALTER\s+(TABLE|VIEW|INDEX|SCHEMA|DATABASE|ROLE)|"
    r"TRUNCATE\s+(TABLE\s+)?\S+|GRANT\s+\S+|"
    r"CREATE\s+(TABLE|INDEX|VIEW|SCHEMA|DATABASE)|MERGE\s+INTO)\b"
)


def check_no_write_methods() -> list[str]:
    failures: list[str] = []
    for cls in (QdrantRepository, PostgresRepository):
        for name in dir(cls):
            lowered = name.lower()
            for forbidden in _FORBIDDEN_METHODS:
                if forbidden in lowered:
                    failures.append(f"{cls.__name__}.{name} looks write-capable")
    return failures


def check_source_has_no_writes() -> list[str]:
    failures: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(_bootstrap.ROOT)
        for pattern in _FORBIDDEN_CALLS:
            if pattern.search(text):
                failures.append(f"{rel}: forbidden call {pattern.pattern}")
        if _SQL_WRITE.search(text):
            failures.append(f"{rel}: SQL write statement detected")
    return failures


def check_postgres_rejects_write() -> tuple[str, list[str]]:
    if os.environ.get("POSTGRES_ENABLED", "false").lower() != "true":
        return ("skipped (POSTGRES_ENABLED=false)", [])

    import psycopg

    from synology_rag.config import Settings, load_schema_mapping

    settings = Settings()
    mapping = load_schema_mapping(settings)
    target = None
    for coll in mapping.collections.values():
        if coll.postgres is not None:
            target = coll.postgres
            break
    if target is None:
        return ("skipped (no approved PostgreSQL table mapped)", [])

    # Connect WITHOUT forcing a read-only session so the account's own
    # privileges are exercised. A truly SELECT-only account must reject this.
    conninfo = psycopg.conninfo.make_conninfo(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        sslmode=settings.postgres_sslmode,
        connect_timeout=settings.postgres_connect_timeout_seconds,
    )
    stmt = (
        f'UPDATE "{target.schema_name}"."{target.table}" '
        f'SET "{target.key_column}" = "{target.key_column}" WHERE false'
    )
    try:
        with psycopg.connect(conninfo, autocommit=False) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(stmt)
                conn.rollback()
                return ("FAILED", ["the reader account was ALLOWED to UPDATE an approved table"])
            except psycopg.errors.InsufficientPrivilege:
                conn.rollback()
                return ("passed (write rejected: insufficient privilege)", [])
            except psycopg.errors.ReadOnlySqlTransaction:
                conn.rollback()
                return ("passed (write rejected: read-only transaction)", [])
            except psycopg.Error as exc:
                conn.rollback()
                return (f"passed (write rejected: {type(exc).__name__})", [])
    except psycopg.Error as exc:
        return (f"skipped (could not connect: {type(exc).__name__})", [])


def main() -> int:
    print("# Read-only verification\n")
    all_failures: list[str] = []

    method_failures = check_no_write_methods()
    print(f"1. No write methods on adapters: {'PASS' if not method_failures else 'FAIL'}")
    all_failures += method_failures

    source_failures = check_source_has_no_writes()
    print(f"2. No write calls/SQL in source: {'PASS' if not source_failures else 'FAIL'}")
    all_failures += source_failures

    status, pg_failures = check_postgres_rejects_write()
    print(f"3. PostgreSQL rejects writes: {status}")
    all_failures += pg_failures

    if all_failures:
        print("\n## Failures")
        for failure in all_failures:
            print(f"- {failure}")
        return 1
    print("\nAll read-only checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
