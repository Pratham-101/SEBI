"""Autonomous orchestration — AI operations manager."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.orm import Session

from app.models.escalation_record import EscalationRecord
from app.models.obligation import Obligation
from app.models.workflow_state import WorkflowState
from app.sla.engine import SlaEngine
from app.services.devrev.comments import DevRevCommentService
from app.services.devrev.tasks import DevRevTaskService
from app.war_room.orchestrator import WarRoomOrchestrator

logger = structlog.get_logger(__name__)


class AutonomousOrchestrator:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._sla = SlaEngine(db)
        self._comments = DevRevCommentService()
        self._tasks = DevRevTaskService()

    def run_cycle(self) -> dict:
        stats = {
            "overdue_flagged": 0,
            "stale_escalated": 0,
            "followups_sent": 0,
            "workflows_reopened": 0,
        }

        overdue = self._sla.scan_overdue()
        stats["overdue_flagged"] = len(overdue)
        for item in overdue:
            self._followup_obligation(item["id"])

        stats["stale_escalated"] = self._escalate_stale_workflows()
        stats["followups_sent"] = self._followup_unresolved_obligations()
        stats["workflows_reopened"] = self._reopen_overdue_workflows()

        logger.info("autonomous_cycle_complete", **stats)
        return stats

    def _followup_obligation(self, obligation_id: int) -> None:
        ob = self._db.get(Obligation, obligation_id)
        if not ob or not ob.devrev_work_id:
            return
        self._comments.add_comment(
            work_id=ob.devrev_work_id,
            body=f"⏰ **Autonomous SLA Alert** — Obligation #{obligation_id} is overdue. Team: {ob.owner_team}",
        )

    def _escalate_stale_workflows(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        rows = (
            self._db.query(WorkflowState)
            .filter(
                WorkflowState.workflow_type == "war_room",
                WorkflowState.current_stage == "active",
                WorkflowState.updated_at < cutoff,
            )
            .all()
        )
        count = 0
        for wf in rows:
            wf.current_stage = "escalated"
            esc = EscalationRecord(
                notification_id=wf.notification_id,
                escalation_level="stale_war_room",
                reason="War room inactive >48h — autonomous escalation",
                status="active",
                devrev_work_id=wf.devrev_parent_work_id,
            )
            self._db.add(esc)
            if wf.devrev_parent_work_id:
                self._comments.add_comment(
                    work_id=wf.devrev_parent_work_id,
                    body="🚨 **Autonomous Escalation** — War room stale. Executive review required.",
                )
            count += 1
        self._db.commit()
        return count

    def _followup_unresolved_obligations(self) -> int:
        rows = (
            self._db.query(Obligation)
            .filter(Obligation.status.in_(("open", "in_progress", "assigned", "overdue", "escalated")))
            .limit(20)
            .all()
        )
        sent = 0
        for ob in rows:
            if ob.devrev_work_id:
                self._tasks.create_issue(
                    title=f"[Follow-up] Obligation #{ob.id}",
                    body=f"Autonomous follow-up: {ob.description[:300]}",
                    tags=["autonomous", "follow-up"],
                )
                sent += 1
        return sent

    def _reopen_overdue_workflows(self) -> int:
        rows = (
            self._db.query(WorkflowState)
            .filter(WorkflowState.current_stage == "escalated")
            .limit(10)
            .all()
        )
        for wf in rows:
            wf.current_stage = "active"
            meta = json.loads(wf.metadata_json or "{}")
            meta["reopened_at"] = datetime.now(timezone.utc).isoformat()
            wf.metadata_json = json.dumps(meta)
        self._db.commit()
        return len(rows)
