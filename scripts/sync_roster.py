#!/usr/bin/env python3
"""Upsert data/roster.json into the team_members table.

Run after editing data/roster.json (see scripts/list_devrev_users.py to get the
DevRev user ids). The pipeline also syncs the roster on startup, but this lets
you refresh it without restarting the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import init_db, open_db_session
from app.services.routing.assignment import AssignmentEngine


def main() -> int:
    init_db()
    db = open_db_session()
    try:
        written = AssignmentEngine(db).sync_roster()
        print(f"Roster synced: {written} member(s) written to team_members.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
