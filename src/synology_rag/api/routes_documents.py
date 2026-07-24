"""Document, chunk, and collection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from synology_rag.api.auth import require_api_key
from synology_rag.api.deps import get_service
from synology_rag.api.schemas import (
    CollectionInfoModel,
    CollectionsResponseModel,
    DocumentMetadataModel,
    SearchResponseModel,
)
from synology_rag.retrieval.service import RetrievalService

router = APIRouter(prefix="/api/v1", tags=["documents"], dependencies=[Depends(require_api_key)])


@router.get("/documents/{document_id}", response_model=DocumentMetadataModel)
async def get_document(
    document_id: str, service: RetrievalService = Depends(get_service)
) -> DocumentMetadataModel:
    doc = await service.get_document_metadata(document_id)
    return DocumentMetadataModel.from_domain(doc)


@router.get("/chunks/{chunk_id}", response_model=SearchResponseModel)
async def get_chunk(
    chunk_id: str,
    neighbours_before: int = Query(default=1, ge=0),
    neighbours_after: int = Query(default=1, ge=0),
    service: RetrievalService = Depends(get_service),
) -> SearchResponseModel:
    response = await service.get_chunk_context(
        chunk_id, neighbours_before=neighbours_before, neighbours_after=neighbours_after
    )
    return SearchResponseModel.from_domain(response)


@router.get("/collections", response_model=CollectionsResponseModel)
async def list_collections(
    service: RetrievalService = Depends(get_service),
) -> CollectionsResponseModel:
    infos = await service.list_collections()
    return CollectionsResponseModel(
        collections=[CollectionInfoModel.from_domain(i) for i in infos]
    )
