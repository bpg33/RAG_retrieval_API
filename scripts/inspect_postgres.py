#!/usr/bin/env python3
"""Read-only PostgreSQL discovery.

Lists tables/views and their columns in the configured schema using catalogue
reads only, inside a read-only transaction. No DDL/DML is issued.

Usage:
    python scripts/inspect_postgres.py

Paste the output into docs/discovery-report.md.
"""

from __future__ import annotations

import os

import _bootstrap

_bootstrap.load_env()

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402


def _conninfo() -> str:
    return psycopg.conninfo.make_conninfo(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", ""),
        user=os.environ.get("POSTGRES_USER", ""),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        sslmode=os.environ.get("POSTGRES_SSLMODE", "prefer"),
        connect_timeout=int(os.environ.get("POSTGRES_CONNECT_TIMEOUT_SECONDS", "5")),
        options="-c default_transaction_read_only=on -c statement_timeout=10000",
    )


def main() -> int:
    schema = os.environ.get("POSTGRES_SCHEMA", "public")
    print("# PostgreSQL discovery (read-only)\n")
    print(f"- schema: {schema}\n")

    with psycopg.connect(_conninfo(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = %s ORDER BY table_type, table_name"
            ),
            (schema,),
        )
        tables = cur.fetchall()
        print(f"## Tables and views ({len(tables)})\n")
        for table_name, table_type in tables:
            print(f"### {table_name} ({table_type})\n")
            cur.execute(
                sql.SQL(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s "
                    "ORDER BY ordinal_position"
                ),
                (schema, table_name),
            )
            for col_name, data_type, nullable in cur.fetchall():
                null = "NULL" if nullable == "YES" else "NOT NULL"
                print(f"- {col_name}: {data_type} {null}")
            print()

    print("_Read-only discovery complete. No data was modified._")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
