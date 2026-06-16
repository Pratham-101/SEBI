"""Celery background tasks."""

from __future__ import annotations

import structlog

from app.core.database import SessionLocal
from app.services.pipeline.orchestrator import PipelineOrchestrator
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="sebi.run_pipeline", bind=True, max_retries=3)
def run_pipeline_task(self) -> dict:
    db = SessionLocal()
    try:
        orchestrator = PipelineOrchestrator(db)
        return orchestrator.run()
    except Exception as exc:
        logger.exception("celery_pipeline_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()
