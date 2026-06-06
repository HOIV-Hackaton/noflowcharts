from fastapi import Depends
from sqlmodel import Session

from app.db.session import get_session
from app.services.run_manager import RunManager


def get_run_manager(session: Session = Depends(get_session)) -> RunManager:
    return RunManager(session)
