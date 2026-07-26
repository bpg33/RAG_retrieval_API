"""Unit tests for request validation and clamping."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from synology_rag.domain.errors import (
    InvalidRequestError,
    UnknownCollectionError,
    UnsupportedFilterError,
)
from synology_rag.domain.models import SearchRequest
from synology_rag.retrieval.validation import validate_search_request
from tests.conftest import make_settings

KNOWN = {"file_type", "folder"}


def _settings(**kw: object):
    return make_settings(**kw)


def test_empty_query_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        validate_search_request(SearchRequest(query="   "), _settings(), known_filter_names=KNOWN)


def test_null_bytes_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        validate_search_request(
            SearchRequest(query="a\x00b"), _settings(), known_filter_names=KNOWN
        )


def test_query_too_long_rejected() -> None:
    settings = _settings(max_query_length=10)
    with pytest.raises(InvalidRequestError):
        validate_search_request(
            SearchRequest(query="x" * 11), settings, known_filter_names=KNOWN
        )


def test_limit_clamped_with_warning() -> None:
    settings = _settings(max_search_limit=5, default_search_limit=5)
    result = validate_search_request(
        SearchRequest(query="q", limit=100), settings, known_filter_names=KNOWN
    )
    assert result.limit == 5
    assert any("reduced to the maximum" in w for w in result.warnings)


def test_default_limit_applied_when_none() -> None:
    settings = _settings(default_search_limit=7)
    result = validate_search_request(
        SearchRequest(query="q"), settings, known_filter_names=KNOWN
    )
    assert result.limit == 7


def test_neighbours_clamped() -> None:
    settings = _settings(max_neighbours_before=2, max_neighbours_after=2)
    result = validate_search_request(
        SearchRequest(query="q", neighbours_before=9, neighbours_after=9),
        settings,
        known_filter_names=KNOWN,
    )
    assert result.neighbours_before == 2
    assert result.neighbours_after == 2


def test_unknown_collection_rejected() -> None:
    with pytest.raises(UnknownCollectionError):
        validate_search_request(
            SearchRequest(query="q", collections=["nope"]),
            _settings(),
            known_filter_names=KNOWN,
        )


def test_unsupported_filter_rejected() -> None:
    with pytest.raises(UnsupportedFilterError):
        validate_search_request(
            SearchRequest(query="q", metadata_filters={"password": "x"}),
            _settings(),
            known_filter_names=KNOWN,
        )


def test_malformed_date_range_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        validate_search_request(
            SearchRequest(
                query="q",
                date_from=datetime(2025, 5, 1, tzinfo=UTC),
                date_to=datetime(2025, 1, 1, tzinfo=UTC),
            ),
            _settings(),
            known_filter_names=KNOWN,
        )


def test_collections_default_to_allowlist() -> None:
    settings = _settings(qdrant_allowed_collections="documents")
    result = validate_search_request(
        SearchRequest(query="q"), settings, known_filter_names=KNOWN
    )
    assert result.collections == ["documents"]
