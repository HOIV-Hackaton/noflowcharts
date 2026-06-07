from collections.abc import Generator
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path and raw_path != ":memory:":
        Path(raw_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().sqlite_database_url
    _ensure_sqlite_parent(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = create_db_engine()


def init_db(db_engine: Engine = engine) -> None:
    SQLModel.metadata.create_all(db_engine)
    _ensure_runtime_columns(db_engine)


def _ensure_runtime_columns(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    tables = set(inspector.get_table_names())
    with db_engine.begin() as connection:
        if "action" in tables:
            columns = {column["name"] for column in inspector.get_columns("action")}
            if "write_preview" not in columns:
                connection.execute(text("ALTER TABLE action ADD COLUMN write_preview JSON"))
        if "terminalcommand" in tables:
            columns = {column["name"] for column in inspector.get_columns("terminalcommand")}
            if "write_preview" not in columns:
                connection.execute(text("ALTER TABLE terminalcommand ADD COLUMN write_preview JSON"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
