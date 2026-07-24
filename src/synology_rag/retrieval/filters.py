"""Build engine-internal Qdrant filters from validated requests.

Only *mapped* payload keys ever appear in a :class:`QueryFilter`. Public filter
names from the request are translated to payload keys via the collection's
schema mapping; a name with no mapping in a given collection simply does not
apply there. No client string is ever used as a raw Qdrant filter.
"""

from __future__ import annotations

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


def build_query_filter(
    request: ValidatedRequest, coll: CollectionMapping
) -> QueryFilter:
    match: list[MatchCondition] = []
    ranges: list[RangeCondition] = []

    filter_keys = coll.resolved_filters()

    file_type_key = filter_keys.get("file_type") or coll.payload.file_type
    if request.file_types and file_type_key:
        match.append(MatchCondition(key=file_type_key, values=list(request.file_types)))

    folder_key = filter_keys.get("folder") or coll.payload.folder
    if request.folders and folder_key:
        match.append(MatchCondition(key=folder_key, values=list(request.folders)))

    for name, value in request.metadata_filters.items():
        # Skip the two shortcut names handled above to avoid double conditions.
        if name in ("file_type", "folder") and name not in filter_keys:
            continue
        key = filter_keys.get(name)
        if key is None:
            continue  # not applicable to this collection
        values = value if isinstance(value, list) else [value]
        match.append(MatchCondition(key=key, values=list(values)))

    modified_key = coll.payload.modified_at
    if (request.date_from or request.date_to) and modified_key:
        ranges.append(
            RangeCondition(key=modified_key, gte=request.date_from, lte=request.date_to)
        )

    return QueryFilter(must_match=match, must_range=ranges)
