from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.errors import AppError, to_http_exception
from app.db.session import get_session
from app.schemas.knowledge import (
    KnowledgeIngestRequest,
    KnowledgeIngestResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    KnowledgeSeedRequest,
    KnowledgeSeedResponse,
)
from app.services.knowledge import KnowledgeService


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def get_knowledge_service_dependency(session: Session = Depends(get_session)) -> KnowledgeService:
    return KnowledgeService(session)


@router.post("/ingest", response_model=KnowledgeIngestResponse)
def ingest_knowledge(
    request: KnowledgeIngestRequest,
    service: KnowledgeService = Depends(get_knowledge_service_dependency),
) -> KnowledgeIngestResponse:
    try:
        return service.ingest(request)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/seed", response_model=KnowledgeSeedResponse)
def seed_knowledge(
    request: KnowledgeSeedRequest,
    service: KnowledgeService = Depends(get_knowledge_service_dependency),
) -> KnowledgeSeedResponse:
    try:
        return service.seed(request.items)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/search", response_model=list[KnowledgeSearchResult])
def search_knowledge(
    request: KnowledgeSearchRequest,
    service: KnowledgeService = Depends(get_knowledge_service_dependency),
) -> list[KnowledgeSearchResult]:
    try:
        return service.search(request.query, chunk_type=request.chunk_type, top_k=request.top_k)
    except AppError as exc:
        raise to_http_exception(exc) from exc
