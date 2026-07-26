"""Request validation and clamping.

Produces a trusted :class:`ValidatedRequest` from an untrusted
:class:`SearchRequest`: it rejects malformed input, clamps values to configured
maxima (adding warnings), resolves the collection allowlist, and confirms every
requested filter maps to a known public field. Clients can never reach Qdrant or
SQL with anything not validated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from synology_rag.config import Settings
from synology_rag.domain.errors import (
    InvalidRequestError,
    UnknownCollectionError,
    UnsupportedFilterError,
)
from synology_rag.domain.models import SearchRequest

FilterValue = str | int | float | bool | list[object]


@dataclass(slots=True)
class ValidatedRequest:
    query: str
    limit: int
    collections: list[str]
    include_neighbours: bool
    neighbours_before: int
    neighbours_after: int
    minimum_score: float | None
    folders: list[str] | None
    file_types: list[str] | None
    date_from: datetime | None
    date_to: datetime | None
    metadata_filters: dict[str, FilterValue]
    warnings: list[str] = field(default_factory=list)


def _clean_query(query: str) -> str:
    if "\x00" in query:
        raise InvalidRequestError("The query contains invalid control characters.")
    try:
        query.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise InvalidRequestError("The query contains invalid Unicode.") from exc
    trimmed = query.strip()
    if not trimmed:
        raise InvalidRequestError("The query must not be empty.")
    return trimmed


def _resolve_collections(
    requested: list[str] | None, allowed: list[str]
) -> list[str]:
    if not requested:
        return list(allowed)
    allowed_set = set(allowed)
    unknown = [c for c in requested if c not in allowed_set]
    if unknown:
        raise UnknownCollectionError(
            f"Unknown or disallowed collection(s): {sorted(unknown)}. "
            f"Allowed: {sorted(allowed)}."
        )
    # Preserve request order, drop duplicates.
    seen: set[str] = set()
    resolved: list[str] = []
    for collection in requested:
        if collection not in seen:
            seen.add(collection)
            resolved.append(collection)
    return resolved


def _as_str_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return [str(v).strip() for v in values if str(v).strip()]


def validate_search_request(
    request: SearchRequest,
    settings: Settings,
    *,
    known_filter_names: set[str],
) -> ValidatedRequest:
    """Validate and clamp a search request.

    ``known_filter_names`` is the union of public filter names across the
    resolved collections; any ``metadata_filters`` key outside it is rejected.
    """
    warnings: list[str] = []
    query = _clean_query(request.query)
    if len(query) > settings.max_query_length:
        raise InvalidRequestError(
            f"The query exceeds the maximum length of {settings.max_query_length} characters."
        )

    collections = _resolve_collections(request.collections, settings.allowed_collections)

    limit = request.limit if request.limit is not None else settings.default_search_limit
    if limit < 1:
        raise InvalidRequestError("`limit` must be at least 1.")
    if limit > settings.max_search_limit:
        warnings.append(
            f"limit {limit} reduced to the maximum of {settings.max_search_limit}."
        )
        limit = settings.max_search_limit

    nb_raw = (
        request.neighbours_before
        if request.neighbours_before is not None
        else settings.default_neighbours_before
    )
    na_raw = (
        request.neighbours_after
        if request.neighbours_after is not None
        else settings.default_neighbours_after
    )
    nb = _clamp_neighbours(nb_raw, settings.max_neighbours_before, "before", warnings)
    na = _clamp_neighbours(na_raw, settings.max_neighbours_after, "after", warnings)

    if request.date_from and request.date_to and request.date_from > request.date_to:
        raise InvalidRequestError("date_from must not be later than date_to.")

    metadata_filters: dict[str, FilterValue] = dict(request.metadata_filters or {})
    unsupported = sorted(k for k in metadata_filters if k not in known_filter_names)
    if unsupported:
        raise UnsupportedFilterError(
            f"Unsupported filter field(s): {unsupported}. "
            f"Supported: {sorted(known_filter_names)}."
        )

    minimum_score = (
        request.minimum_score
        if request.minimum_score is not None
        else settings.default_minimum_score
    )

    return ValidatedRequest(
        query=query,
        limit=limit,
        collections=collections,
        include_neighbours=request.include_neighbours,
        neighbours_before=nb,
        neighbours_after=na,
        minimum_score=minimum_score,
        folders=_as_str_list(request.folders),
        file_types=_as_str_list(request.file_types),
        date_from=request.date_from,
        date_to=request.date_to,
        metadata_filters=metadata_filters,
        warnings=warnings,
    )


def _clamp_neighbours(value: int, maximum: int, label: str, warnings: list[str]) -> int:
    if value < 0:
        raise InvalidRequestError(f"neighbours_{label} must not be negative.")
    if value > maximum:
        warnings.append(f"neighbours_{label} {value} reduced to the maximum of {maximum}.")
        return maximum
    return value
