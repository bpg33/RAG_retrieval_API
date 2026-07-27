"""The retrieval service: orchestrates the read-only retrieval pipeline.

This is the single business-logic entry point. REST and MCP adapters call these
methods and add no retrieval logic of their own, guaranteeing equivalent results
across protocols.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from time import perf_counter
from typing import TypeVar

from ulid import ULID

from synology_rag.config import SchemaMapping, Settings
from synology_rag.domain.errors import (
    ChunkNotFoundError,
    ConfigurationError,
    DocumentNotFoundError,
    QdrantUnavailableError,
    RetrievalError,
    RetrievalTimeoutError,
)
from synology_rag.domain.models import (
    CollectionInfo,
    DocumentMetadata,
    RetrievedChunk,
    SearchRequest,
    SearchResponse,
)
from synology_rag.domain.ports import (
    EmbeddingProvider,
    MatchCondition,
    MetadataRepository,
    QueryFilter,
    VectorHit,
    VectorRepository,
)
from synology_rag.retrieval.candidate import Candidate
from synology_rag.retrieval.citations import build_citations
from synology_rag.retrieval.context_budget import apply_context_budget
from synology_rag.retrieval.deduplication import deduplicate
from synology_rag.retrieval.embeddings import generate_query_embedding
from synology_rag.retrieval.filters import (
    build_query_filter,
    known_filter_names,
    unsupported_filter_warnings,
)
from synology_rag.retrieval.metadata import (
    _coerce_datetime,
    chunk_from_hit,
    enrich_candidates,
)
from synology_rag.retrieval.neighbours import expand_neighbours
from synology_rag.retrieval.query_normalisation import normalise_query
from synology_rag.retrieval.ranking import rank_primary
from synology_rag.retrieval.retry import with_retries
from synology_rag.retrieval.validation import validate_search_request
from synology_rag.retrieval.versions import collapse_versions

IdFactory = Callable[[], str]
_T = TypeVar("_T")


def _default_id() -> str:
    return str(ULID())


class RetrievalService:
    def __init__(
        self,
        *,
        settings: Settings,
        mapping: SchemaMapping,
        embedding_provider: EmbeddingProvider,
        vector_repo: VectorRepository,
        metadata_repo: MetadataRepository | None = None,
        id_factory: IdFactory = _default_id,
    ) -> None:
        self._settings = settings
        self._mapping = mapping
        self._embed = embedding_provider
        self._vectors = vector_repo
        self._metadata = metadata_repo
        self._new_id = id_factory
        self._known_filters = known_filter_names(mapping, settings.allowed_collections)

    # -- Search --------------------------------------------------------------
    async def search(self, request: SearchRequest) -> SearchResponse:
        try:
            return await asyncio.wait_for(
                self._search(request), timeout=self._settings.search_timeout_seconds
            )
        except TimeoutError as exc:
            raise RetrievalTimeoutError(
                "The search timed out. Please try again."
            ) from exc

    async def _search(self, request: SearchRequest) -> SearchResponse:
        start = perf_counter()
        search_id = self._new_id()

        validated = validate_search_request(
            request, self._settings, known_filter_names=self._known_filters
        )
        normalised = normalise_query(validated.query)
        vector = await self._retry(
            lambda: generate_query_embedding(self._embed, normalised.normalised)
        )

        warnings = list(validated.warnings)
        searched_mappings = [self._mapping.for_collection(c) for c in validated.collections]
        warnings.extend(unsupported_filter_warnings(validated, searched_mappings))

        candidate_limit = self._candidate_limit(validated.limit)
        candidates: list[Candidate] = []
        failed: list[str] = []
        for collection in validated.collections:
            coll = self._mapping.for_collection(collection)
            search = partial(
                self._vectors.search,
                collection=collection,
                vector=vector,
                vector_name=coll.vector_name,
                limit=candidate_limit,
                query_filter=build_query_filter(validated, coll),
                score_threshold=validated.minimum_score,
            )
            try:
                hits = await self._retry(search)
            except QdrantUnavailableError:
                if not self._settings.partial_results_on_collection_error:
                    raise
                failed.append(collection)
                warnings.append(
                    f"Collection '{collection}' was unavailable and was skipped; "
                    "results may be incomplete."
                )
                continue
            candidates.extend(chunk_from_hit(hit, coll) for hit in hits)

        if failed and len(failed) == len(validated.collections):
            raise QdrantUnavailableError("All searched collections are currently unavailable.")

        deduped = deduplicate(candidates)
        ranked = rank_primary(deduped)

        # Hydrate a working set (with buffer) so liveness drops can be backfilled,
        # then cap to the requested limit. For Qdrant-only collections hydration is
        # a no-op and this simply slices the top results.
        working_size = min(len(ranked), max(validated.limit * 2, validated.limit + 10))
        working = ranked[:working_size]
        working, hydrate_warnings = await enrich_candidates(
            working, self._mapping, self._metadata
        )
        warnings.extend(hydrate_warnings)

        if self._settings.collapse_duplicate_versions:
            working, collapsed = collapse_versions(
                working, similarity_threshold=self._settings.duplicate_version_similarity
            )
            if collapsed:
                warnings.append(
                    f"Collapsed {collapsed} near-duplicate document version(s); "
                    "showing the most recent of each."
                )

        primaries = working[: validated.limit]
        # Assign primary ranks before neighbour expansion so neighbours inherit.
        for index, cand in enumerate(primaries, start=1):
            cand.chunk.rank = index

        neighbours: list[Candidate] = []
        if validated.include_neighbours:
            neighbours = await expand_neighbours(
                primaries,
                vector_repo=self._vectors,
                metadata_repo=self._metadata,
                mapping=self._mapping,
                neighbours_before=validated.neighbours_before,
                neighbours_after=validated.neighbours_after,
            )
            if neighbours:
                neighbours, n_warnings = await enrich_candidates(
                    neighbours, self._mapping, self._metadata
                )
                warnings.extend(n_warnings)

        ordered = _interleave(primaries, neighbours)
        budget = apply_context_budget(
            ordered,
            max_total_chunks=self._settings.max_total_chunks,
            max_total_characters=self._settings.max_returned_characters,
            max_characters_per_chunk=self._settings.max_characters_per_chunk,
        )
        warnings.extend(budget.warnings)
        final_chunks = budget.chunks

        citations = build_citations(final_chunks)
        if not final_chunks:
            warnings.append(
                "No indexed passages matched the query and filters; the evidence is "
                "insufficient to answer."
            )

        elapsed_ms = int((perf_counter() - start) * 1000)
        return SearchResponse(
            query=normalised.original,
            results=final_chunks,
            citations=citations,
            search_id=search_id,
            elapsed_ms=elapsed_ms,
            warnings=list(dict.fromkeys(warnings)),  # de-duplicate, preserve order
            truncated=budget.truncated,
        )

    def _candidate_limit(self, limit: int) -> int:
        oversampled = limit * self._settings.candidate_multiplier
        return max(limit, min(oversampled, self._settings.max_candidates))

    async def _retry(self, factory: Callable[[], Awaitable[_T]]) -> _T:
        return await with_retries(
            factory,
            retries=self._settings.max_retries,
            base_delay=self._settings.retry_base_delay_seconds,
        )

    # -- Document metadata ---------------------------------------------------
    async def get_document_metadata(self, document_id: str) -> DocumentMetadata:
        document_id = (document_id or "").strip()
        if not document_id:
            raise DocumentNotFoundError("A document id is required.")
        for collection in self._settings.allowed_collections:
            coll = self._mapping.for_collection(collection)
            doc_key = coll.payload.document_id
            if not doc_key:
                continue
            hits = await self._vectors.scroll(
                collection=collection,
                scroll_filter=QueryFilter(
                    must_match=[MatchCondition(key=doc_key, values=[document_id])]
                ),
                limit=1,
            )
            if not hits:
                continue
            return await self._document_from_hit(hits[0], collection)
        raise DocumentNotFoundError(f"No document found with id {document_id!r}.")

    async def _document_from_hit(self, hit: VectorHit, collection: str) -> DocumentMetadata:
        coll = self._mapping.for_collection(collection)
        cand = chunk_from_hit(hit, coll)
        kept, _ = await enrich_candidates([cand], self._mapping, self._metadata)
        cand = kept[0] if kept else cand
        chunk = cand.chunk
        created = _coerce_datetime(
            hit.payload.get(coll.payload.created_at) if coll.payload.created_at else None
        )
        return DocumentMetadata(
            document_id=chunk.document_id,
            display_name=chunk.filename or chunk.title or chunk.document_id,
            title=chunk.title,
            file_type=chunk.file_type,
            source_uri=chunk.source_uri,
            modified_at=chunk.modified_at,
            created_at=created,
            collection=collection,
        )

    # -- Chunk context -------------------------------------------------------
    async def get_chunk_context(
        self, chunk_id: str, *, neighbours_before: int, neighbours_after: int
    ) -> SearchResponse:
        chunk_id = (chunk_id or "").strip()
        if not chunk_id:
            raise ChunkNotFoundError("A chunk id is required.")
        nb = min(max(neighbours_before, 0), self._settings.max_neighbours_before)
        na = min(max(neighbours_after, 0), self._settings.max_neighbours_after)

        start = perf_counter()
        found = await self._find_chunk(chunk_id)
        if found is None:
            raise ChunkNotFoundError(f"No chunk found with id {chunk_id!r}.")
        _collection, cand = found

        kept, warnings = await enrich_candidates([cand], self._mapping, self._metadata)
        cand = kept[0] if kept else cand
        cand.chunk.rank = 1

        neighbours = await expand_neighbours(
            [cand],
            vector_repo=self._vectors,
            metadata_repo=self._metadata,
            mapping=self._mapping,
            neighbours_before=nb,
            neighbours_after=na,
        )
        if neighbours:
            neighbours, n_warnings = await enrich_candidates(
                neighbours, self._mapping, self._metadata
            )
            warnings.extend(n_warnings)

        ordered = _interleave([cand], neighbours)
        budget = apply_context_budget(
            ordered,
            max_total_chunks=self._settings.max_total_chunks,
            max_total_characters=self._settings.max_returned_characters,
            max_characters_per_chunk=self._settings.max_characters_per_chunk,
        )
        warnings.extend(budget.warnings)
        citations = build_citations(budget.chunks)
        return SearchResponse(
            query="",
            results=budget.chunks,
            citations=citations,
            search_id=self._new_id(),
            elapsed_ms=int((perf_counter() - start) * 1000),
            warnings=warnings,
            truncated=budget.truncated,
        )

    async def _find_chunk(self, chunk_id: str) -> tuple[str, Candidate] | None:
        for collection in self._settings.allowed_collections:
            coll = self._mapping.for_collection(collection)
            if coll.payload.chunk_id:
                hits = await self._vectors.scroll(
                    collection=collection,
                    scroll_filter=QueryFilter(
                        must_match=[MatchCondition(key=coll.payload.chunk_id, values=[chunk_id])]
                    ),
                    limit=1,
                )
            else:
                hits = await self._vectors.retrieve(collection=collection, ids=[chunk_id])
            if hits:
                return collection, chunk_from_hit(hits[0], coll)
        return None

    # -- Collections ---------------------------------------------------------
    async def list_collections(self) -> list[CollectionInfo]:
        infos: list[CollectionInfo] = []
        for name in self._settings.allowed_collections:
            coll = self._mapping.for_collection(name)
            info = CollectionInfo(name=name, description=coll.description)
            try:
                stats = await self._vectors.collection_stats(name)
                info.vector_dimensions = stats.size_for(coll.vector_name)
                info.distance = stats.distance
                info.points_count = stats.points_count
            except RetrievalError:
                pass  # description-only if the store is briefly unavailable
            infos.append(info)
        return infos

    # -- Health / startup ----------------------------------------------------
    async def readiness(self) -> dict[str, bool | None]:
        result: dict[str, bool | None] = {}
        try:
            first = self._settings.allowed_collections[0]
            result["qdrant"] = await self._vectors.collection_exists(first)
        except Exception:
            result["qdrant"] = False
        result["postgres"] = (
            await self._metadata.health() if self._metadata is not None else None
        )
        try:
            result["embedding"] = await self._embed.health()
        except Exception:
            result["embedding"] = False
        return result

    async def verify_startup(self) -> list[str]:
        """Confirm collections exist and vector dimensions match. Fails closed."""
        notes: list[str] = []
        expected_dims = self._settings.embedding_dimensions
        for name in self._settings.allowed_collections:
            coll = self._mapping.for_collection(name)
            if not await self._vectors.collection_exists(name):
                raise ConfigurationError(f"Configured collection {name!r} does not exist.")
            stats = await self._vectors.collection_stats(name)
            actual = stats.size_for(coll.vector_name)
            if expected_dims is not None and actual is not None and actual != expected_dims:
                raise ConfigurationError(
                    f"Collection {name!r} vector size {actual} does not match "
                    f"EMBEDDING_DIMENSIONS {expected_dims}."
                )
            if actual is None:
                notes.append(
                    f"Could not determine vector size for {name!r}; skipped dimension check."
                )
        return notes


def _interleave(primaries: list[Candidate], neighbours: list[Candidate]) -> list[RetrievedChunk]:
    """Order results as primary hits, each surrounded by its own neighbours."""
    by_parent: dict[str, list[Candidate]] = {}
    for neighbour in neighbours:
        parent_id = neighbour.chunk.parent_result_chunk_id or ""
        by_parent.setdefault(parent_id, []).append(neighbour)

    ordered: list[RetrievedChunk] = []
    for primary in primaries:
        kids = by_parent.get(primary.chunk.chunk_id, [])
        parent_seq = primary.sequence
        before = [k for k in kids if _is_before(k.sequence, parent_seq)]
        after = [k for k in kids if not _is_before(k.sequence, parent_seq)]
        # Sort by sequence; None-sequence neighbours sort last without comparing
        # None to None (which would raise TypeError).
        before.sort(key=_sequence_sort_key)
        after.sort(key=_sequence_sort_key)
        ordered.extend(c.chunk for c in before)
        ordered.append(primary.chunk)
        ordered.extend(c.chunk for c in after)
    return ordered


def _is_before(seq: int | None, parent_seq: int | None) -> bool:
    if seq is None or parent_seq is None:
        return False
    return seq < parent_seq


def _sequence_sort_key(cand: Candidate) -> tuple[bool, int]:
    """Order by sequence ascending; unknown sequences last. Never compares None."""
    return (cand.sequence is None, cand.sequence if cand.sequence is not None else 0)
