"""Recover SQLite when WAL sidecar files are corrupted after hard kills."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def resolve_sqlite_path(database_url: str) -> Path | None:
    """Resolve sqlite URL to an absolute filesystem path."""
    if not database_url.startswith("sqlite"):
        return None

    raw = database_url.removeprefix("sqlite:///")
    if raw.startswith("/"):
        return Path(raw)

    project_root = Path(__file__).resolve().parents[2]
    if raw.startswith("./"):
        return (project_root / raw[2:]).resolve()
    return (project_root / raw).resolve()


def normalize_sqlite_url(database_url: str) -> str:
    """Always use an absolute sqlite URL so cwd changes cannot break the DB."""
    db_path = resolve_sqlite_path(database_url)
    if db_path is None:
        return database_url
    return f"sqlite:///{db_path}"


def recover_sqlite_if_needed(database_url: str) -> None:
    """If SQLite cannot open, quarantine bad WAL/SHM files and retry."""
    db_path = resolve_sqlite_path(database_url)
    if db_path is None or not db_path.exists():
        return

    if _is_healthy(db_path):
        return

    _quarantine_sidecars(db_path)
    if not _is_healthy(db_path):
        raise RuntimeError(f"SQLite database is unreadable after WAL recovery: {db_path}")

    _apply_safe_pragmas(db_path)
    logger.info("sqlite_recover_complete", db_path=str(db_path))


def prepare_sqlite_for_dev(database_url: str) -> None:
    """Checkpoint WAL, switch to DELETE journal mode, remove sidecar files."""
    db_path = resolve_sqlite_path(database_url)
    if db_path is None:
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        return

    recover_sqlite_if_needed(database_url)

    conn = sqlite3.connect(os.fspath(db_path), timeout=30.0)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()
    finally:
        conn.close()

    _remove_sidecars(db_path)
    logger.info("sqlite_prepared", db_path=str(db_path), journal_mode="DELETE")


def checkpoint_sqlite(database_url: str) -> None:
    """Flush pending writes on shutdown."""
    db_path = resolve_sqlite_path(database_url)
    if db_path is None or not db_path.exists():
        return

    try:
        conn = sqlite3.connect(os.fspath(db_path), timeout=10.0)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        logger.warning("sqlite_checkpoint_failed", error=str(exc))


def _quarantine_sidecars(db_path: Path) -> None:
    logger.warning("sqlite_recover_start", db_path=str(db_path))
    stamp = str(int(time.time()))
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.parent / f"{db_path.name}{suffix}"
        if not sidecar.exists():
            continue
        backup = sidecar.with_name(f"{sidecar.name}.corrupt.{stamp}")
        sidecar.rename(backup)
        logger.warning(
            "sqlite_sidecar_quarantined",
            path=str(sidecar),
            backup=str(backup),
        )


def _remove_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = db_path.parent / f"{db_path.name}{suffix}"
        if sidecar.exists():
            sidecar.unlink()


def _apply_safe_pragmas(db_path: Path) -> None:
    conn = sqlite3.connect(os.fspath(db_path), timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()
    finally:
        conn.close()


def _is_healthy(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(os.fspath(db_path), timeout=30.0)
        try:
            conn.execute("SELECT 1")
            conn.execute("PRAGMA integrity_check")
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row and row[0] == "ok")
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False
