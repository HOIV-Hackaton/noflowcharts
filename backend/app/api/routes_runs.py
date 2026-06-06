from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session

from app.core.errors import AppError, to_http_exception
from app.db.session import engine, get_session
from app.schemas.runs import ActionDecision, ActionEdit, AuditEventRead, RiskConfirmation, RunCreate, RunStateRead, ValidationConfirmation
from app.services.run_manager import RunManager


router = APIRouter(prefix="/api/runs", tags=["runs"])


def get_run_manager(session: Session = Depends(get_session)) -> RunManager:
    return RunManager(session)


@router.post("", response_model=RunStateRead)
def create_run(request: RunCreate, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.start_run(request.ticket_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.get("/{run_id}", response_model=RunStateRead)
def get_run(run_id: str, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.state(run_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/confirm-ssh", response_model=RunStateRead)
def confirm_ssh(run_id: str, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.confirm_ssh(run_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/next", response_model=RunStateRead)
def next_action(run_id: str, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.propose_next(run_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/confirm-risk", response_model=RunStateRead)
def confirm_risk(run_id: str, request: RiskConfirmation, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.confirm_risk(run_id, request.confirmation_text, action_id=request.action_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/approve", response_model=RunStateRead)
def approve_action(
    run_id: str,
    request: ActionDecision,
    background_tasks: BackgroundTasks,
    manager: RunManager = Depends(get_run_manager),
) -> RunStateRead:
    try:
        state, action_id = manager.approve(run_id, action_id=request.action_id)
        background_tasks.add_task(_execute_action_background, run_id, action_id)
        return state
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/reject", response_model=RunStateRead)
def reject_action(run_id: str, request: ActionDecision, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.reject(run_id, action_id=request.action_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/edit", response_model=RunStateRead)
def edit_action(run_id: str, request: ActionEdit, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.edit(run_id, request.command, intent=request.intent, action_id=request.action_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/retry", response_model=RunStateRead)
def retry_action(run_id: str, request: ActionDecision, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.retry(run_id, action_id=request.action_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/safer-alternative", response_model=RunStateRead)
def safer_alternative(run_id: str, request: ActionDecision, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.request_safer_alternative(run_id, action_id=request.action_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/validation/confirm", response_model=RunStateRead)
def confirm_validation(run_id: str, request: ValidationConfirmation, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.confirm_validation(run_id, request.evidence)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.post("/{run_id}/abort", response_model=RunStateRead)
def abort_run(run_id: str, manager: RunManager = Depends(get_run_manager)) -> RunStateRead:
    try:
        return manager.abort(run_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


@router.get("/{run_id}/audit", response_model=list[AuditEventRead])
def get_audit(run_id: str, manager: RunManager = Depends(get_run_manager)):
    try:
        return manager.audit_events(run_id)
    except AppError as exc:
        raise to_http_exception(exc) from exc


def _execute_action_background(run_id: str, action_id: int) -> None:
    with Session(engine) as session:
        RunManager(session).execute_action(run_id, action_id)
