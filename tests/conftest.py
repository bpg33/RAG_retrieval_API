"""Shared pytest fixtures.

Builds a fully working retrieval service backed by in-memory fakes and a small
deterministic corpus, so unit/contract/security tests need no live services.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from synology_rag.adapters.embedding_provider import FakeEmbeddingProvider
from synology_rag.config import Settings, load_schema_mapping
from synology_rag.retrieval.service import RetrievalService
from tests.fakes import FakePoint, InMemoryMetadataRepository, InMemoryVectorRepository

DIMS = 64
EXAMPLE_MAPPING = "config/schema_mapping.example.yaml"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "embedding_provider": "fake",
        "embedding_dimensions": DIMS,
        "embedding_normalise": True,
        "qdrant_allowed_collections": "documents",
        "schema_mapping_file": EXAMPLE_MAPPING,
        "postgres_enabled": False,
        "default_search_limit": 10,
        "max_search_limit": 25,
        "max_total_chunks": 20,
        "max_returned_characters": 40000,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.fixture
def embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dimensions=DIMS, normalise=True)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def mapping(settings: Settings):
    return load_schema_mapping(settings)


def _embed(embedder: FakeEmbeddingProvider, text: str) -> list[float]:
    return asyncio.run(embedder.embed_query(text))


def _point(
    embedder: FakeEmbeddingProvider,
    *,
    chunk_id: str,
    document_id: str,
    text: str,
    filename: str,
    file_type: str,
    seq: int,
    page: int | None = None,
    section: str | None = None,
    sheet: str | None = None,
    folder: str | None = None,
    modified_at: str | None = None,
) -> FakePoint:
    payload = {
        "text": text,
        "document_id": document_id,
        "chunk_id": chunk_id,
        "filename": filename,
        "file_type": file_type,
        "chunk_index": seq,
        "page_number": page,
        "section": section,
        "sheet_name": sheet,
        "folder": folder,
        "modified_at": modified_at,
    }
    return FakePoint(id=chunk_id, vector=_embed(embedder, text), payload=payload)


@pytest.fixture
def vector_repo(embedder: FakeEmbeddingProvider) -> InMemoryVectorRepository:
    points = [
        _point(
            embedder,
            chunk_id="chunk-1a",
            document_id="doc-1",
            text="Introduction to the asset tagging programme and its objectives.",
            filename="Asset Tagging Programme Review.pdf",
            file_type="pdf",
            seq=0,
            page=1,
            section="Introduction",
            folder="consulting",
            modified_at="2025-11-14T09:30:00+00:00",
        ),
        _point(
            embedder,
            chunk_id="chunk-1b",
            document_id="doc-1",
            text=(
                "The programme identified recurring implementation risks in asset "
                "tagging projects such as poor data quality and scope creep."
            ),
            filename="Asset Tagging Programme Review.pdf",
            file_type="pdf",
            seq=1,
            page=8,
            section="Implementation risks",
            folder="consulting",
            modified_at="2025-11-14T09:30:00+00:00",
        ),
        _point(
            embedder,
            chunk_id="chunk-1c",
            document_id="doc-1",
            text="Recommendations to mitigate asset tagging implementation risks.",
            filename="Asset Tagging Programme Review.pdf",
            file_type="pdf",
            seq=2,
            page=9,
            section="Recommendations",
            folder="consulting",
            modified_at="2025-11-14T09:30:00+00:00",
        ),
        _point(
            embedder,
            chunk_id="chunk-2a",
            document_id="doc-2",
            text="Quarterly budget figures and headcount for the finance team.",
            filename="Finance Budget.xlsx",
            file_type="xlsx",
            seq=0,
            sheet="Q1",
            folder="finance",
            modified_at="2025-03-01T00:00:00+00:00",
        ),
    ]
    return InMemoryVectorRepository(collections={"documents": points})


@pytest.fixture
def metadata_repo() -> InMemoryMetadataRepository:
    return InMemoryMetadataRepository()


@pytest.fixture
def service(
    settings: Settings,
    mapping,
    embedder: FakeEmbeddingProvider,
    vector_repo: InMemoryVectorRepository,
) -> RetrievalService:
    counter = {"n": 0}

    def id_factory() -> str:
        counter["n"] += 1
        return f"test-{counter['n']:06d}"

    return RetrievalService(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=None,
        id_factory=id_factory,
    )


def build_test_container(
    settings: Settings,
    vector_repo: InMemoryVectorRepository,
    embedder: FakeEmbeddingProvider,
    metadata_repo: InMemoryMetadataRepository | None = None,
):
    from synology_rag.container import AppContainer

    mapping = load_schema_mapping(settings)
    service = RetrievalService(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=metadata_repo,
    )
    return AppContainer(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=metadata_repo,
        service=service,
    )


@pytest.fixture
def container(
    settings: Settings,
    mapping,
    embedder: FakeEmbeddingProvider,
    vector_repo: InMemoryVectorRepository,
    service: RetrievalService,
):
    from synology_rag.container import AppContainer

    return AppContainer(
        settings=settings,
        mapping=mapping,
        embedding_provider=embedder,
        vector_repo=vector_repo,
        metadata_repo=None,
        service=service,
    )


@pytest.fixture
def client(container):
    from fastapi.testclient import TestClient

    from synology_rag.api.app import create_app

    app = create_app(container=container)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
