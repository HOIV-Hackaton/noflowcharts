from collections.abc import Generator
from pathlib import Path
import sqlite3

from sqlalchemy import event
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


def _load_sqlite_vec(dbapi_connection, connection_record=None) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    import sqlite_vec

    dbapi_connection.enable_load_extension(True)
    try:
        sqlite_vec.load(dbapi_connection)
    finally:
        dbapi_connection.enable_load_extension(False)


def create_db_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().sqlite_database_url
    _ensure_sqlite_parent(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    db_engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        event.listen(db_engine, "connect", _load_sqlite_vec)
    return db_engine


engine = create_db_engine()


def init_db(db_engine: Engine = engine) -> None:
    SQLModel.metadata.create_all(db_engine)
    _ensure_runtime_columns(db_engine)
    ensure_knowledge_vector_table(db_engine)


def ensure_knowledge_vector_table(db_engine: Engine = engine) -> None:
    with db_engine.begin() as connection:
        raw_connection = getattr(connection.connection, "driver_connection", None)
        if raw_connection is not None:
            _load_sqlite_vec(raw_connection)
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_vectors "
                "USING vec0(embedding float[1536])"
            )
        )


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
