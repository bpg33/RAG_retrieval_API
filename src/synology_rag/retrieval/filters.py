"""Build engine-internal Qdrant filters from validated requests.

Only *mapped* payload keys ever appear in a :class:`QueryFilter`. Public filter
names from the request are translated to payload keys via the collection's
schema mapping; a name with no mapping in a given collection simply does not
apply there. No client string is ever used as a raw Qdrant filter.
"""

from __future__ import annotations

from collections.abc import Callable

from synology_rag.config import CollectionMapping, SchemaMapping
from synology_rag.domain.ports import MatchCondition, QueryFilter, RangeCondition
from synology_rag.retrieval.validation import ValidatedRequest


def known_filter_names(mapping: SchemaMapping, collections: list[str]) -> set[str]:
    """Union of public filter names across the given collections.

    Also includes the built-in ``folder``/``file_type`` shortcuts when the
    collection exposes the corresponding payload field.
    """
    names: set[str] = set()
    for name in collections:
        coll = mapping.for_collection(name)
        names.update(coll.filters.keys())
        if coll.payload.folder:
            names.add("folder")
        if coll.payload.file_type:
            names.add("file_type")
    return names


def build_query_filter(request: ValidatedRequest, coll: CollectionMapping) -> QueryFilter:
    # Accumulate matches per payload key so a shortcut (file_types/folders) and an
    # equivalent metadata_filters entry do not produce redundant conditions.
    matches: dict[str, list[object]] = {}
    filter_keys = coll.resolved_filters()

    def add(key: str, values: list[object]) -> None:
        bucket = matches.setdefault(key, [])
        for value in values:
            if value not in bucket:
                bucket.append(value)

    file_type_key = filter_keys.get("file_type") or coll.payload.file_type
    if request.file_types and file_type_key:
        add(file_type_key, list(request.file_types))

    folder_key = filter_keys.get("folder") or coll.payload.folder
    if request.folders and folder_key:
        add(folder_key, list(request.folders))

    for name, value in request.metadata_filters.items():
        key = filter_keys.get(name)
        if key is None:
            continue  # not applicable to this collection
        values = value if isinstance(value, list) else [value]
        add(key, list(values))

    match = [MatchCondition(key=key, values=values) for key, values in matches.items()]

    ranges: list[RangeCondition] = []
    modified_key = coll.payload.modified_at
    if (request.date_from or request.date_to) and modified_key:
        ranges.append(
            RangeCondition(key=modified_key, gte=request.date_from, lte=request.date_to)
        )

    return QueryFilter(must_match=match, must_range=ranges)


def unsupported_filter_warnings(
    request: ValidatedRequest, colls: list[CollectionMapping]
) -> list[str]:
    """Warn about requested filters that apply to none of the searched collections.

    A filter that is valid overall (it maps in some allowed collection) can still
    be a silent no-op if the user searched a different subset. Surfacing this
    avoids "why isn't my filter working" confusion.
    """
    warnings: list[str] = []

    def any_collection(predicate: Callable[[CollectionMapping], bool]) -> bool:
        return any(predicate(c) for c in colls)

    if request.file_types and not any_collection(
        lambda c: bool(c.resolved_filters().get("file_type") or c.payload.file_type)
    ):
        warnings.append("The file_types filter matched no searched collection and was ignored.")

    if request.folders and not any_collection(
        lambda c: bool(c.resolved_filters().get("folder") or c.payload.folder)
    ):
        warnings.append("The folders filter matched no searched collection and was ignored.")

    if (request.date_from or request.date_to) and not any_collection(
        lambda c: bool(c.payload.modified_at)
    ):
        warnings.append("The date range filter matched no searched collection and was ignored.")

    for name in request.metadata_filters:
        if not any(name in c.resolved_filters() for c in colls):
            warnings.append(f"The '{name}' filter matched no searched collection and was ignored.")

    return warnings
