#!/usr/bin/env python3
"""One-off: ingest top SEBI listing rows that were falsely skipped (e.g. May 19)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.services.pipeline.orchestrator import PipelineOrchestrator

configure_logging()


def main() -> int:
    db = SessionLocal()
    try:
        stats = PipelineOrchestrator(db).run()
        print("Pipeline completed:", stats)
        return 0 if stats.get("errors", 0) == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
