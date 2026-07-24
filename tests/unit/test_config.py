"""Unit tests for typed configuration and schema mapping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from synology_rag.config import (
    MetadataSource,
    PostgresCollectionMapping,
    load_schema_mapping,
)
from tests.conftest import make_settings


def test_non_local_bind_requires_acknowledgement() -> None:
    with pytest.raises(ValidationError):
        make_settings(bind_host="192.168.1.5")


def test_non_local_bind_allowed_with_flag() -> None:
    settings = make_settings(bind_host="192.168.1.5", allow_non_local_bind=True)
    assert settings.bind_is_local is False


def test_missing_embedding_model_fails_for_real_provider() -> None:
    with pytest.raises(ValidationError):
        make_settings(embedding_provider="openai_compatible", embedding_model=None)


def test_missing_dimensions_fails_for_real_provider() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            embedding_provider="openai_compatible",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=None,
        )


def test_allowed_collections_parsing() -> None:
    settings = make_settings(qdrant_allowed_collections=" a , b ,, c ")
    assert settings.allowed_collections == ["a", "b", "c"]


def test_postgres_required_but_disabled_raises(tmp_path) -> None:
    mapping_file = tmp_path / "m.yaml"
    mapping_file.write_text(
        "collections:\n"
        "  documents:\n"
        "    metadata_source: postgres\n"
        "    postgres:\n"
        "      schema: public\n"
        "      table: docs_v\n"
        "      document_id_column: document_id\n"
        "      columns: {filename: filename}\n"
    )
    settings = make_settings(
        schema_mapping_file=str(mapping_file), postgres_enabled=False
    )
    with pytest.raises(ValueError, match="PostgreSQL"):
        load_schema_mapping(settings)


def test_postgres_identifier_validation_rejects_injection() -> None:
    with pytest.raises(ValidationError):
        PostgresCollectionMapping(
            schema="public", table="docs; DROP TABLE users", document_id_column="id"
        )


def test_dimensions_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_settings(embedding_provider="fake", embedding_dimensions=0)


def test_default_search_limit_cannot_exceed_max() -> None:
    with pytest.raises(ValidationError):
        make_settings(default_search_limit=100, max_search_limit=10)


def test_metadata_source_enum_default_is_qdrant() -> None:
    settings = make_settings()
    mapping = load_schema_mapping(settings)
    assert mapping.for_collection("documents").metadata_source is MetadataSource.QDRANT
