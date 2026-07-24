"""Composition root.

Builds the retrieval service from settings by wiring the concrete read-only
adapters, and owns their lifecycle. Both the REST app and the MCP server use
this so they share one identical engine configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from synology_rag.adapters.embedding_provider import build_embedding_provider
from synology_rag.adapters.postgres_repository import PostgresRepository
from synology_rag.adapters.qdrant_repository import QdrantRepository
from synology_rag.config import SchemaMapping, Settings, load_schema_mapping
from synology_rag.domain.ports import EmbeddingProvider, MetadataRepository, VectorRepository
from synology_rag.observability.logging import get_logger
from synology_rag.retrieval.service import RetrievalService

log = get_logger(__name__)


@dataclass
class AppContainer:
    settings: Settings
    mapping: SchemaMapping
    embedding_provider: EmbeddingProvider
    vector_repo: VectorRepository
    metadata_repo: MetadataRepository | None
    service: RetrievalService

    async def startup(self) -> None:
        if isinstance(self.metadata_repo, PostgresRepository):
            await self.metadata_repo.open()
        if self.settings.startup_verify_collections:
            notes = await self.service.verify_startup()
            for note in notes:
                log.warning("startup.verify", note=note)
            log.info(
                "startup.verify.ok",
                collections=self.settings.allowed_collections,
                embedding_model=self.settings.embedding_model or "fake",
                dimensions=self.settings.embedding_dimensions,
            )

    async def shutdown(self) -> None:
        closer = getattr(self.embedding_provider, "aclose", None)
        if closer is not None:
            await closer()
        if isinstance(self.vector_repo, QdrantRepository):
            await self.vector_repo.aclose()
        if isinstance(self.metadata_repo, PostgresRepository):
            await self.metadata_repo.aclose()


def build_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or Settings()
    mapping = load_schema_mapping(settings)
    embedding_provider = build_embedding_provider(settings)
    vector_repo: VectorRepository = QdrantRepository.from_settings(settings)
    metadata_repo: MetadataRepository | None = (
        PostgresRepository.from_settings(settings, mapping)
        if settings.postgres_enabled
        else None
    )
    service = RetrievalService(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedding_provider,
        vector_repo=vector_repo,
        metadata_repo=metadata_repo,
    )
    return AppContainer(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedding_provider,
        vector_repo=vector_repo,
        metadata_repo=metadata_repo,
        service=service,
    )
