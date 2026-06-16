from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.workers.tasks import run_pipeline_task

router = APIRouter(tags=["operations"])


class ManualRunResponse(BaseModel):
    status: str
    task_id: str | None = None
    message: str


@router.post("/trigger/manual-run", response_model=ManualRunResponse)
def manual_run(sync: bool | None = None) -> ManualRunResponse:
    """Trigger pipeline manually. Runs inline when sync=true or USE_SYNC_PIPELINE=true."""
    settings = get_settings()
    run_inline = sync if sync is not None else settings.use_sync_pipeline
    if run_inline:
        from app.core.database import SessionLocal
        from app.services.pipeline.orchestrator import PipelineOrchestrator

        db = SessionLocal()
        try:
            stats = PipelineOrchestrator(db).run()
            return ManualRunResponse(
                status="completed",
                message=str(stats),
            )
        finally:
            db.close()

    result = run_pipeline_task.delay()
    return ManualRunResponse(
        status="queued",
        task_id=result.id,
        message="Pipeline enqueued on Celery worker",
    )
