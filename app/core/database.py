"""SQLAlchemy database session management."""

from __future__ import annotations

from collections.abc import Generator

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
_database_url = settings.database_url

if _is_sqlite:
    from app.core.sqlite_recover import (
        normalize_sqlite_url,
        prepare_sqlite_for_dev,
        recover_sqlite_if_needed,
    )

    _database_url = normalize_sqlite_url(settings.database_url)
    prepare_sqlite_for_dev(_database_url)

_connect_args: dict = {"check_same_thread": False, "timeout": 30.0} if _is_sqlite else {}

_engine_kwargs: dict = {"connect_args": _connect_args}
if _is_sqlite:
    _engine_kwargs["poolclass"] = StaticPool
else:
    _engine_kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)

engine = create_engine(_database_url, **_engine_kwargs)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=DELETE")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def reset_sqlite_engine() -> None:
    """Dispose pooled connections after recovery."""
    engine.dispose()


def ensure_sqlite_connection() -> None:
    """Verify SQLite is readable; recover and reset pool if needed."""
    if not _is_sqlite:
        return

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except DatabaseError:
        logger.warning("sqlite_connection_unhealthy_recovering")
        recover_sqlite_if_needed(_database_url)
        reset_sqlite_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))


def open_db_session() -> Session:
    """Open a DB session after verifying SQLite health (for background jobs)."""
    ensure_sqlite_connection()
    return SessionLocal()


def get_db() -> Generator[Session, None, None]:
    db = open_db_session()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401 — register all ORM models

    Base.metadata.create_all(bind=engine)
    from app.core.migrate import migrate_sqlite_columns

    migrate_sqlite_columns()
    _sync_roster_on_startup()


def _sync_roster_on_startup() -> None:
    """Seed team_members from data/roster.json so assignment works out of the box."""
    if not get_settings().assignment_enabled:
        return
    try:
        from app.services.routing.assignment import AssignmentEngine

        db = SessionLocal()
        try:
            AssignmentEngine(db).sync_roster()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 — roster sync is best-effort at startup
        logger.warning("roster_sync_on_startup_failed", exc_info=True)


def shutdown_db() -> None:
    """Flush SQLite writes on graceful shutdown."""
    if not _is_sqlite:
        return

    from app.core.sqlite_recover import checkpoint_sqlite

    checkpoint_sqlite(_database_url)
    reset_sqlite_engine()
