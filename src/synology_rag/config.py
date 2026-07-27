"""Typed, fail-closed application configuration.

Two layers of configuration exist:

* :class:`Settings` - connection details, secrets, and limits, loaded from
  environment variables / ``.env`` via ``pydantic-settings``.
* :class:`SchemaMapping` - the shape of the *existing* index (Qdrant payload
  keys, PostgreSQL columns, neighbour ordering), loaded from a YAML file.

Keeping the discovered index layout in typed configuration (rather than scattered
constants) is a core requirement of the specification (section 25): the retrieval
engine adapts to whatever the discovery phase records without code changes.

All identifiers that could ever reach SQL composition (schema/table/column names)
are validated against a strict identifier pattern here, so untrusted or malformed
values can never form part of a query.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Domain fields that a Qdrant payload / PostgreSQL row may supply.
PAYLOAD_FIELDS = frozenset(
    {
        "text",
        "document_id",
        "chunk_id",
        "filename",
        "title",
        "page_number",
        "slide_number",
        "sheet_name",
        "section",
        "file_type",
        "source_uri",
        "modified_at",
        "created_at",
        "folder",
        "sequence",
        "active_flag",
    }
)


def _empty_to_none(value: Any) -> Any:
    """Treat blank environment values as unset (``None``)."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _validate_identifier(value: str, *, what: str) -> str:
    if not _SQL_IDENTIFIER.match(value):
        raise ValueError(
            f"{what} {value!r} is not a valid SQL identifier "
            "(letters, digits, underscore; not starting with a digit)"
        )
    return value


OptFloat = Annotated[float | None, BeforeValidator(_empty_to_none)]
OptInt = Annotated[int | None, BeforeValidator(_empty_to_none)]
OptStr = Annotated[str | None, BeforeValidator(_empty_to_none)]


class EmbeddingProviderName(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"
    FAKE = "fake"


class MetadataSource(StrEnum):
    QDRANT = "qdrant"
    POSTGRES = "postgres"
    BOTH = "both"


# --------------------------------------------------------------------------- #
# Schema mapping (YAML)                                                        #
# --------------------------------------------------------------------------- #
class PayloadMapping(BaseModel):
    """Maps domain fields to Qdrant payload keys for one collection.

    A ``None`` value means the field is absent from the payload.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = "text"
    document_id: str | None = "document_id"
    chunk_id: str | None = None
    filename: str | None = "filename"
    title: str | None = None
    page_number: str | None = None
    slide_number: str | None = None
    sheet_name: str | None = None
    section: str | None = None
    file_type: str | None = None
    source_uri: str | None = None
    modified_at: str | None = None
    created_at: str | None = None
    folder: str | None = None
    sequence: str | None = None
    active_flag: str | None = None


class PostgresCollectionMapping(BaseModel):
    """Maps domain fields to columns of an approved PostgreSQL table/view.

    Identifiers here come from trusted configuration and are validated as safe
    SQL identifiers so they can be composed with ``psycopg.sql.Identifier``.

    ``lookup_key`` selects whether rows are matched per chunk or per document:
    use ``chunk_id`` when per-chunk data (e.g. the chunk text) lives in
    PostgreSQL keyed by chunk id. ``drop_if_missing`` removes a result whose row
    is absent, which is how liveness is enforced when the approved view already
    excludes removed/superseded rows.
    """

    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(default="public", alias="schema")
    table: str
    lookup_key: Literal["document_id", "chunk_id"] = "document_id"
    key_column: str = "document_id"
    columns: dict[str, str] = Field(default_factory=dict)
    drop_if_missing: bool = False
    # Column for the document id, used only for PostgreSQL neighbour expansion
    # (WHERE document_id = ? AND sequence BETWEEN ...). Requires a `sequence`
    # column in `columns`.
    document_id_column: str | None = None

    @field_validator("schema_name", "table", "key_column")
    @classmethod
    def _valid_identifier(cls, v: str) -> str:
        return _validate_identifier(v, what="PostgreSQL identifier")

    @field_validator("document_id_column")
    @classmethod
    def _valid_optional_identifier(cls, v: str | None) -> str | None:
        return _validate_identifier(v, what="PostgreSQL identifier") if v else v

    @field_validator("columns")
    @classmethod
    def _valid_columns(cls, v: dict[str, str]) -> dict[str, str]:
        for field, column in v.items():
            if field not in PAYLOAD_FIELDS:
                raise ValueError(
                    f"Unknown domain field {field!r} in postgres.columns; "
                    f"allowed: {sorted(PAYLOAD_FIELDS)}"
                )
            _validate_identifier(column, what="PostgreSQL column")
        return v


class SourceUriTemplate(BaseModel):
    """Builds a client-openable document URI from a stored path field.

    Reconstructs, per result, a path the user's machine can open (e.g. a UNC
    path to the Synology share, or a ``file://`` URL) from the indexed path,
    which is otherwise a container/host path that is not directly openable. The
    values here are trusted configuration, not client input.
    """

    model_config = ConfigDict(extra="forbid")

    from_payload: str  # payload key holding the raw stored path
    strip_prefix: str = ""  # remove this leading path prefix (e.g. "/data/")
    add_prefix: str = ""  # prepend this (e.g. "\\\\192.168.1.59\\share\\")
    separator: str | None = None  # replace "/" in the path with this (e.g. "\\")
    # For PDFs, append "#page=N" so viewers that support it open at the page.
    pdf_page_anchor: bool = False


class CollectionMapping(BaseModel):
    """Everything the engine needs to interpret one Qdrant collection."""

    model_config = ConfigDict(extra="forbid")

    description: str = ""
    vector_name: str | None = None
    metadata_source: MetadataSource = MetadataSource.QDRANT
    payload: PayloadMapping = Field(default_factory=PayloadMapping)
    filters: dict[str, str] = Field(default_factory=dict)
    postgres: PostgresCollectionMapping | None = None
    source_uri: SourceUriTemplate | None = None
    # Where neighbouring chunks come from: "qdrant" (adjacent by a sequence
    # payload key) or "postgres" (adjacent by a sequence column, for indexes
    # whose chunk order lives only in PostgreSQL).
    neighbour_source: Literal["qdrant", "postgres"] = "qdrant"

    @model_validator(mode="after")
    def _check_neighbour_source(self) -> CollectionMapping:
        if self.neighbour_source == "postgres":
            pg = self.postgres
            if pg is None or pg.document_id_column is None or "sequence" not in pg.columns:
                raise ValueError(
                    "neighbour_source='postgres' requires a postgres mapping with "
                    "document_id_column set and a 'sequence' column mapped"
                )
        return self

    @model_validator(mode="after")
    def _check_consistency(self) -> CollectionMapping:
        needs_pg = self.metadata_source in (MetadataSource.POSTGRES, MetadataSource.BOTH)
        if needs_pg and self.postgres is None:
            raise ValueError(
                "metadata_source requires PostgreSQL but no `postgres` mapping was provided"
            )
        return self

    def resolved_filters(self) -> dict[str, str]:
        """Public filter name -> payload key (validated non-empty keys)."""
        return dict(self.filters)


class SchemaMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collections: dict[str, CollectionMapping]

    def for_collection(self, name: str) -> CollectionMapping:
        try:
            return self.collections[name]
        except KeyError as exc:  # pragma: no cover - guarded upstream
            raise KeyError(f"No schema mapping for collection {name!r}") from exc

    @classmethod
    def from_file(cls, path: Path) -> SchemaMapping:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        defaults: dict[str, Any] = raw.get("defaults") or {}
        collections_in: dict[str, Any] = raw.get("collections") or {}
        merged: dict[str, Any] = {}
        for name, spec in collections_in.items():
            spec = dict(spec or {})
            for key, value in defaults.items():
                spec.setdefault(key, value)
            merged[name] = spec
        return cls(collections=merged)


# --------------------------------------------------------------------------- #
# Settings (environment)                                                       #
# --------------------------------------------------------------------------- #
class Settings(BaseSettings):
    """Environment-driven settings. Fails closed on invalid values."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    allow_non_local_bind: bool = False
    local_api_key: OptStr = None
    enable_rest_api: bool = True
    enable_mcp: bool = True
    enable_source_file_read: bool = False
    log_content: bool = False

    # Qdrant
    qdrant_url: str = "http://synology.local:6333"
    qdrant_api_key: OptStr = None
    qdrant_allowed_collections: str = "documents"
    qdrant_timeout_seconds: float = 5.0
    qdrant_prefer_grpc: bool = False
    # Rescore with full-precision vectors when the collection uses scalar/product
    # quantization (int8). Improves accuracy at a small latency cost; harmless on
    # non-quantized collections.
    qdrant_rescore: bool = True

    # PostgreSQL
    postgres_enabled: bool = False
    postgres_host: str = "synology.local"
    postgres_port: int = 5432
    postgres_db: OptStr = None
    postgres_user: str = "rag_retrieval_reader"
    postgres_password: OptStr = None
    postgres_schema: str = "public"
    postgres_sslmode: str = "prefer"
    postgres_statement_timeout_ms: int = 3000
    postgres_connect_timeout_seconds: int = 5
    postgres_pool_min: int = 0
    postgres_pool_max: int = 4

    # Embeddings
    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.OPENAI_COMPATIBLE
    embedding_model: OptStr = None
    embedding_dimensions: OptInt = None
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: OptStr = None
    embedding_timeout_seconds: float = 15.0
    embedding_normalise: bool = False

    # Retrieval limits / context budget
    default_search_limit: int = 10
    max_search_limit: int = 25
    default_minimum_score: OptFloat = None
    max_query_length: int = 4000
    default_neighbours_before: int = 1
    default_neighbours_after: int = 1
    max_neighbours_before: int = 2
    max_neighbours_after: int = 2
    max_total_chunks: int = 20
    max_returned_characters: int = 40000
    max_characters_per_chunk: int = 0
    # Candidate oversampling for dense search (headroom for dedup/threshold).
    candidate_multiplier: int = 4
    max_candidates: int = 100
    # Collapse near-duplicate versions of the same document (e.g. "deck v2..v6")
    # across results, keeping the most recent (by modified date, else best score).
    collapse_duplicate_versions: bool = False
    duplicate_version_similarity: float = 0.9

    # Reliability
    search_timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_base_delay_seconds: float = 0.2
    # When multiple collections are searched and one is unavailable: if true,
    # return partial results with a warning; if false (default), fail the search.
    partial_results_on_collection_error: bool = False

    # HTTP hardening
    # Maximum accepted request body size in bytes (413 above this).
    max_request_bytes: int = 65536
    # Comma-separated allowed CORS origins for a local browser chat app.
    # Empty disables CORS entirely (the default; server-to-server needs none).
    cors_allow_origins: str = ""

    # Schema mapping
    schema_mapping_file: str = "config/schema_mapping.yaml"
    startup_verify_collections: bool = True

    # -- Parsed / derived ----------------------------------------------------
    @property
    def allowed_collections(self) -> list[str]:
        return [c.strip() for c in self.qdrant_allowed_collections.split(",") if c.strip()]

    @property
    def bind_is_local(self) -> bool:
        return self.bind_host in _LOCAL_HOSTS

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @field_validator("embedding_dimensions")
    @classmethod
    def _positive_dimensions(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("EMBEDDING_DIMENSIONS must be a positive integer")
        return v

    @field_validator(
        "max_search_limit",
        "default_search_limit",
        "max_total_chunks",
        "candidate_multiplier",
        "max_candidates",
        "max_request_bytes",
    )
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be a positive integer")
        return v

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if not self.allowed_collections:
            raise ValueError("QDRANT_ALLOWED_COLLECTIONS must list at least one collection")
        if self.default_search_limit > self.max_search_limit:
            raise ValueError("DEFAULT_SEARCH_LIMIT cannot exceed MAX_SEARCH_LIMIT")
        if not self.bind_is_local and not self.allow_non_local_bind:
            raise ValueError(
                f"BIND_HOST={self.bind_host!r} is non-local. Set ALLOW_NON_LOCAL_BIND=true "
                "to acknowledge exposing the service beyond localhost."
            )
        if self.embedding_provider != EmbeddingProviderName.FAKE:
            if not self.embedding_model:
                raise ValueError("EMBEDDING_MODEL is required unless EMBEDDING_PROVIDER=fake")
            if self.embedding_dimensions is None:
                raise ValueError(
                    "EMBEDDING_DIMENSIONS is required unless EMBEDDING_PROVIDER=fake"
                )
        if self.postgres_enabled and not self.postgres_db:
            raise ValueError("POSTGRES_DB is required when POSTGRES_ENABLED=true")
        return self


def load_schema_mapping(settings: Settings) -> SchemaMapping:
    """Load and cross-validate the schema mapping against the allowlist."""
    path = Path(settings.schema_mapping_file)
    if not path.exists():
        raise FileNotFoundError(
            f"Schema mapping file not found: {path}. Copy "
            "config/schema_mapping.example.yaml to config/schema_mapping.yaml and "
            "edit it to match your discovery report."
        )
    mapping = SchemaMapping.from_file(path)
    missing = [c for c in settings.allowed_collections if c not in mapping.collections]
    if missing:
        raise ValueError(
            f"Allowed collections without a schema mapping: {missing}. "
            f"Add them to {path} or remove from QDRANT_ALLOWED_COLLECTIONS."
        )
    if settings.postgres_enabled is False:
        for name, coll in mapping.collections.items():
            if coll.metadata_source in (MetadataSource.POSTGRES, MetadataSource.BOTH):
                raise ValueError(
                    f"Collection {name!r} needs PostgreSQL (metadata_source="
                    f"{coll.metadata_source.value}) but POSTGRES_ENABLED=false"
                )
    return mapping
