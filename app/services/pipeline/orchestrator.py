"""End-to-end regulatory intelligence pipeline — delegates to RegOps OS."""

from __future__ import annotations

import time
import uuid

import structlog
from sqlalchemy.orm import Session

from app.agents.coordinator import RegOpsCoordinator
from app.core.config import get_settings
from app.governance.audit import AuditService

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
  """Backward-compatible facade; runs RegOps multi-agent coordinator."""

  def __init__(self, db: Session) -> None:
    self._db = db
    self._coordinator = RegOpsCoordinator(db)
    self._audit = AuditService(db)

  def run(self, *, trace_id: str | None = None) -> dict:
    trace_id = trace_id or uuid.uuid4().hex
    settings = get_settings()

    if settings.regops_multi_agent:
      return self._coordinator.run(trace_id=trace_id)

    logger.warning("regops_multi_agent_disabled")
    return self._coordinator.run(trace_id=trace_id)
