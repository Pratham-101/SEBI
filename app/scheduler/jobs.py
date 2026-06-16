"""APScheduler cron jobs for SEBI monitoring."""

from __future__ import annotations

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.workers.tasks import run_pipeline_task

logger = structlog.get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    settings = get_settings()
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _enqueue_pipeline,
        "interval",
        minutes=settings.cron_interval_minutes,
        id="sebi_monitor",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _run_autonomous_cycle,
        "interval",
        minutes=max(settings.cron_interval_minutes * 2, 10),
        id="autonomous_orchestrator",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _run_followup_cycle,
        "interval",
        minutes=max(settings.cron_interval_minutes * 3, 15),
        id="followup_engine",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "scheduler_started",
        interval_minutes=settings.cron_interval_minutes,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    _scheduler = None


def _enqueue_pipeline() -> None:
    settings = get_settings()
    if settings.use_sync_pipeline:
        logger.info("running_pipeline_inline")
        from app.core.database import open_db_session
        from app.services.pipeline.orchestrator import PipelineOrchestrator

        db = open_db_session()
        try:
            PipelineOrchestrator(db).run()
        finally:
            db.close()
        return

    logger.info("enqueueing_pipeline_via_celery")
    run_pipeline_task.delay()


def _run_followup_cycle() -> None:
    from app.core.database import open_db_session
    from app.orchestration.followup import FollowUpEngine

    db = open_db_session()
    try:
        FollowUpEngine(db).run()
    finally:
        db.close()


def _run_autonomous_cycle() -> None:
    from app.core.database import open_db_session
    from app.orchestration.autonomous import AutonomousOrchestrator

    db = open_db_session()
    try:
        stats = AutonomousOrchestrator(db).run_cycle()
        logger.info("autonomous_cycle_finished", **stats)
    finally:
        db.close()
