"""Autonomous follow-up engine — proactive remediation tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.orm import Session

from app.events.emitter import IntelligenceEmitter
from app.models.obligation import Obligation
from app.models.workflow_state import WorkflowState
from app.services.devrev.comments import DevRevCommentService
from app.sla.engine import SlaEngine

logger = structlog.get_logger(__name__)


class FollowUpEngine:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._sla = SlaEngine(db)
        self._comments = DevRevCommentService()
        self._emitter = IntelligenceEmitter(db)

    def run(self) -> dict:
        stats = {"reminders": 0, "escalations": 0, "reopened": 0, "inactive_flagged": 0}
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(hours=72)

        obligations = (
            self._db.query(Obligation)
            .filter(Obligation.status.in_(("assigned", "in_progress", "acknowledged", "detected")))
            .all()
        )

        for ob in obligations:
            if ob.deadline_at and ob.deadline_at < now + timedelta(days=3):
                self._remind(ob)
                stats["reminders"] += 1
            if ob.updated_at and ob.updated_at < stale_cutoff:
                try:
                    self._sla.transition(ob.id, "escalated", actor="autonomous", notes="Inactivity detected")
                    stats["escalations"] += 1
                    self._emitter.emit(
                        event_type="autonomous_escalation",
                        title=f"Obligation #{ob.id} escalated",
                        narrative=f"Team {ob.owner_team} — no progress in 72h.",
                        severity="warning",
                        notification_id=ob.notification_id,
                    )
                except ValueError:
                    pass

        overdue = self._sla.scan_overdue()
        stats["overdue_scanned"] = len(overdue)

        workflows = (
            self._db.query(WorkflowState)
            .filter(WorkflowState.current_stage == "escalated")
            .all()
        )
        for wf in workflows:
            wf.current_stage = "active"
            stats["reopened"] += 1
            self._emitter.emit(
                event_type="workflow_reopened",
                title="Workflow reactivated",
                narrative=f"War room workflow #{wf.id} reopened for remediation.",
                severity="info",
                notification_id=wf.notification_id,
            )

        self._db.commit()
        logger.info("followup_complete", **stats)
        return stats

    def _remind(self, ob: Obligation) -> None:
        if ob.devrev_work_id:
            self._comments.add_comment(
                work_id=ob.devrev_work_id,
                body=f"📋 **Autonomous Reminder** — Obligation approaching deadline. Owner: {ob.owner_team}",
            )
        self._emitter.emit(
            event_type="followup_reminder",
            title=f"SLA reminder: obligation #{ob.id}",
            narrative=ob.description[:200],
            severity="info",
            notification_id=ob.notification_id,
        )
