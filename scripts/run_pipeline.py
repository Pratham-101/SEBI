#!/usr/bin/env python3
"""Run the RegOps pipeline once (scrape + backlog + DevRev tickets)."""

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
        print("Pipeline completed:")
        for key, value in sorted(stats.items()):
            print(f"  {key}: {value}")
        return 0 if stats.get("errors", 0) == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
