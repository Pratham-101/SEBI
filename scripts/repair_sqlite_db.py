#!/usr/bin/env python3
"""Repair local SQLite database after kill -9 or WAL corruption."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.sqlite_recover import (
    normalize_sqlite_url,
    prepare_sqlite_for_dev,
    recover_sqlite_if_needed,
    resolve_sqlite_path,
)


def main() -> int:
    settings = get_settings()
    url = normalize_sqlite_url(settings.database_url)
    db_path = resolve_sqlite_path(url)
    if db_path is None:
        print("Not a SQLite database URL")
        return 1

    print(f"Repairing: {db_path}")
    recover_sqlite_if_needed(url)
    prepare_sqlite_for_dev(url)

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()

    print(f"integrity_check: {integrity}")
    print(f"notifications: {count}")
    print("Repair complete. Restart uvicorn from the project directory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
