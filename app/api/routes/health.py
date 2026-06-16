from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "sebi-regulatory-intelligence-agent",
        "scheduler": {
            "enabled": True,
            "interval_minutes": settings.cron_interval_minutes,
            "description": (
                f"Every {settings.cron_interval_minutes} minutes the agent scrapes SEBI, "
                "detects new notifications, runs AI analysis, and creates DevRev tickets "
                "(skips duplicates)."
            ),
        },
        "pipeline_mode": "sync" if settings.use_sync_pipeline else "celery",
    }
