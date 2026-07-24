"""Search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from synology_rag.api.auth import require_api_key
from synology_rag.api.deps import get_container, get_service
from synology_rag.api.schemas import SearchRequestModel, SearchResponseModel
from synology_rag.container import AppContainer
from synology_rag.observability import audit
from synology_rag.observability.metrics import metrics
from synology_rag.retrieval.service import RetrievalService

router = APIRouter(prefix="/api/v1", tags=["search"], dependencies=[Depends(require_api_key)])


@router.post("/search", response_model=SearchResponseModel)
async def search(
    body: SearchRequestModel,
    request: Request,
    service: RetrievalService = Depends(get_service),
    container: AppContainer = Depends(get_container),
) -> SearchResponseModel:
    domain_request = body.to_domain()
    response = await service.search(domain_request)

    metrics.increment("search_total")
    metrics.observe_ms("search_latency", response.elapsed_ms)
    if not response.results:
        metrics.increment("search_empty_total")

    audit.record_search(
        client=request.headers.get("X-Client-Id", "rest-api"),
        search_id=response.search_id,
        collections=domain_request.collections or container.settings.allowed_collections,
        document_ids=[c.document_id for c in response.results],
        result_count=len(response.results),
        success=True,
    )
    return SearchResponseModel.from_domain(response)
