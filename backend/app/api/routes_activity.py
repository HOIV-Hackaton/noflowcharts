from fastapi import APIRouter, Depends

from app.api.dependencies import get_run_manager
from app.core.errors import AppError, to_http_exception
from app.schemas.phoenix import Activity, StatusUpdate, Ticket
from app.schemas.runs import ActivityDraftRead, ActivityDraftUpdate, ActivityReviewRequest, ActivitySubmitRequest
from app.services.run_manager import RunManager


router = APIRouter(tags=["activity"])


@router.post("/api/runs/{run_id}/activity/draft", response_model=ActivityDraftRead)
def generate_activity_draft(run_id: str, manager: RunManager = Depends(get_run_manager)) -> ActivityDraftRead:
    try:
        return manager.generate_activity_draft(run_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.patch("/api/runs/{run_id}/activity/draft", response_model=ActivityDraftRead)
def update_activity_draft(run_id: str, request: ActivityDraftUpdate, manager: RunManager = Depends(get_run_manager)) -> ActivityDraftRead:
    try:
        return manager.update_activity_draft(run_id, request)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/runs/{run_id}/activity/review", response_model=ActivityDraftRead)
def review_activity_draft(run_id: str, request: ActivityReviewRequest, manager: RunManager = Depends(get_run_manager)) -> ActivityDraftRead:
    try:
        return manager.review_activity_draft(run_id, approved=request.approved)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/api/runs/{run_id}/activity/submit", response_model=Activity)
def submit_activity(run_id: str, request: ActivitySubmitRequest, manager: RunManager = Depends(get_run_manager)) -> Activity:
    try:
        return manager.submit_activity(run_id, request)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.patch("/api/tickets/{ticket_id}/status", response_model=Ticket)
def set_ticket_status(ticket_id: int, request: StatusUpdate, manager: RunManager = Depends(get_run_manager)) -> Ticket:
    try:
        return manager.phoenix.set_ticket_status(ticket_id, request.status)
    except AppError as exc:
        raise to_http_exception(exc) from exc
