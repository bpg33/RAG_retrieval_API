"""Read-only PostgreSQL metadata repository.

Every query is a parameterised ``SELECT`` composed from *trusted configuration*
identifiers (validated as SQL identifiers in :mod:`synology_rag.config`) using
``psycopg.sql.Identifier``. Client-supplied values are always bound parameters -
never concatenated into SQL, and never used as identifiers.

Read-only is enforced at several layers:

* the connection sets ``default_transaction_read_only=on`` and a
  ``statement_timeout`` via libpq options;
* only SELECT-composing methods exist on this class;
* the database account itself should be a dedicated SELECT-only reader
  (see docs/security.md and scripts/verify_read_only.py).
"""

from __future__ import annotations

from typing import Any, cast

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from synology_rag.config import PostgresCollectionMapping, SchemaMapping, Settings
from synology_rag.domain.errors import PostgresUnavailableError

_TRANSIENT = (psycopg.OperationalError, psycopg.InterfaceError, OSError, ConnectionError)


def build_conninfo(settings: Settings) -> str:
    """Build a libpq conninfo string with read-only + timeout options baked in."""
    options = (
        f"-c default_transaction_read_only=on "
        f"-c statement_timeout={settings.postgres_statement_timeout_ms}"
    )
    return make_conninfo(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        sslmode=settings.postgres_sslmode,
        connect_timeout=settings.postgres_connect_timeout_seconds,
        options=options,
    )


class PostgresRepository:
    """Async, read-only metadata enrichment over approved views/tables."""

    def __init__(self, pool: AsyncConnectionPool, mapping: SchemaMapping) -> None:
        self._pool = pool
        self._mapping = mapping

    @classmethod
    def from_settings(cls, settings: Settings, mapping: SchemaMapping) -> PostgresRepository:
        pool = AsyncConnectionPool(
            conninfo=build_conninfo(settings),
            min_size=settings.postgres_pool_min,
            max_size=settings.postgres_pool_max,
            open=False,
            kwargs={"row_factory": dict_row, "autocommit": True},
        )
        return cls(pool, mapping)

    async def open(self) -> None:
        await self._pool.open(wait=False)

    async def aclose(self) -> None:
        await self._pool.close()

    async def fetch_metadata(
        self, *, collection: str, document_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not document_ids:
            return {}
        coll = self._mapping.for_collection(collection)
        pgm = coll.postgres
        if pgm is None:
            return {}

        query = self._build_select(pgm)
        try:
            async with self._pool.connection() as conn:
                cursor = await conn.execute(query, (list(document_ids),))
                rows = cast(list[dict[str, Any]], await cursor.fetchall())
        except _TRANSIENT as exc:
            raise PostgresUnavailableError(
                "The metadata database is currently unavailable.",
                internal_detail=type(exc).__name__,
            ) from exc

        col_to_field = {column: field for field, column in pgm.columns.items()}
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            doc_id = str(row[pgm.document_id_column])
            fields: dict[str, Any] = {}
            for column, value in row.items():
                if column == pgm.document_id_column:
                    continue
                field = col_to_field.get(column)
                if field is not None and value is not None:
                    fields[field] = value
            result[doc_id] = fields
        return result

    @staticmethod
    def _build_select(pgm: PostgresCollectionMapping) -> sql.Composed:
        select_cols: list[sql.Composable] = [sql.Identifier(pgm.document_id_column)]
        select_cols.extend(sql.Identifier(column) for column in pgm.columns.values())
        return sql.SQL("SELECT {cols} FROM {schema}.{table} WHERE {idcol} = ANY(%s)").format(
            cols=sql.SQL(", ").join(select_cols),
            schema=sql.Identifier(pgm.schema_name),
            table=sql.Identifier(pgm.table),
            idcol=sql.Identifier(pgm.document_id_column),
        )

    async def health(self) -> bool:
        try:
            async with self._pool.connection() as conn:
                await conn.execute("SELECT 1")
        except Exception:
            return False
        return True
