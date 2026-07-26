"""Unit tests for filter building and known-filter discovery."""

from __future__ import annotations

from datetime import UTC, datetime

from synology_rag.config import CollectionMapping, PayloadMapping, Settings, load_schema_mapping
from synology_rag.retrieval.filters import (
    build_query_filter,
    known_filter_names,
    unsupported_filter_warnings,
)
from synology_rag.retrieval.validation import ValidatedRequest
from tests.conftest import make_settings


def _mapping(settings: Settings):
    return load_schema_mapping(settings)


def _validated(**kw: object) -> ValidatedRequest:
    base: dict[str, object] = {
        "query": "q",
        "limit": 10,
        "collections": ["documents"],
        "include_neighbours": False,
        "neighbours_before": 0,
        "neighbours_after": 0,
        "minimum_score": None,
        "folders": None,
        "file_types": None,
        "date_from": None,
        "date_to": None,
        "metadata_filters": {},
        "warnings": [],
    }
    base.update(kw)
    return ValidatedRequest(**base)  # type: ignore[arg-type]


def test_known_filter_names_includes_shortcuts() -> None:
    settings = make_settings()
    names = known_filter_names(_mapping(settings), ["documents"])
    assert "file_type" in names
    assert "folder" in names


def test_file_type_and_folder_map_to_payload_keys() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    qf = build_query_filter(
        _validated(file_types=["pdf", "pptx"], folders=["consulting"]), coll
    )
    keys = {c.key: c.values for c in qf.must_match}
    assert keys["file_type"] == ["pdf", "pptx"]
    assert keys["folder"] == ["consulting"]


def test_date_range_maps_to_modified_at() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    qf = build_query_filter(
        _validated(
            date_from=datetime(2025, 1, 1, tzinfo=UTC),
            date_to=datetime(2025, 12, 31, tzinfo=UTC),
        ),
        coll,
    )
    assert len(qf.must_range) == 1
    assert qf.must_range[0].key == "modified_at"


def test_metadata_filter_applied_when_mapped() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    qf = build_query_filter(_validated(metadata_filters={"file_type": "pdf"}), coll)
    assert any(c.key == "file_type" and c.values == ["pdf"] for c in qf.must_match)


def test_empty_filter_is_empty() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    qf = build_query_filter(_validated(), coll)
    assert qf.is_empty()


def test_shortcut_and_metadata_filter_do_not_duplicate_conditions() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    qf = build_query_filter(
        _validated(file_types=["pdf"], metadata_filters={"file_type": "pdf"}), coll
    )
    file_type_conditions = [c for c in qf.must_match if c.key == "file_type"]
    assert len(file_type_conditions) == 1
    assert file_type_conditions[0].values == ["pdf"]


def test_shortcut_and_metadata_filter_union_values() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    qf = build_query_filter(
        _validated(file_types=["pdf"], metadata_filters={"file_type": "pptx"}), coll
    )
    condition = next(c for c in qf.must_match if c.key == "file_type")
    assert condition.values == ["pdf", "pptx"]


def test_unsupported_filter_warns_when_no_collection_matches() -> None:
    # A collection that exposes no file_type/folder/modified fields.
    bare = CollectionMapping(payload=PayloadMapping(text="text", document_id="document_id"))
    warnings = unsupported_filter_warnings(
        _validated(file_types=["pdf"], folders=["x"]), [bare]
    )
    assert any("file_types" in w for w in warnings)
    assert any("folders" in w for w in warnings)


def test_no_warning_when_filter_supported() -> None:
    settings = make_settings()
    coll = _mapping(settings).for_collection("documents")
    warnings = unsupported_filter_warnings(_validated(file_types=["pdf"]), [coll])
    assert warnings == []
