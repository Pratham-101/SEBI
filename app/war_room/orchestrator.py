"""AI War Room — incident-style compliance coordination for HIGH/CRITICAL."""

from __future__ import annotations

import json

import structlog
from sqlalchemy.orm import Session

from app.models.escalation_record import EscalationRecord
from app.models.workflow_state import WorkflowState
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.devrev.advanced import DevRevAdvancedService
from app.services.devrev.comments import DevRevCommentService
from app.services.devrev.tasks import DevRevTaskService
from app.services.routing.team_router import RoutingDecision

logger = structlog.get_logger(__name__)


class WarRoomOrchestrator:
  def __init__(self, db: Session) -> None:
    self._db = db
    self._comments = DevRevCommentService()
    self._tasks = DevRevTaskService()
    self._advanced = DevRevAdvancedService()

  def activate(
    self,
    *,
    notification_id: int | None,
    work_id: str,
    display_id: str,
    analysis: RegulatoryAnalysisOutput,
    routing: RoutingDecision | None,
    predictions: dict,
    trace_id: str,
  ) -> dict:
    teams = analysis.teams_to_notify[:6]
    body = (
      f"## 🚨 RegOps War Room — {analysis.priority}\n\n"
      f"**Regulation:** {analysis.ticket_title}\n\n"
      f"**Operational exposure:** {predictions.get('operational_exposure', 'n/a')}\n"
      f"**Escalation probability:** {predictions.get('escalation_probability', 'n/a')}\n\n"
      f"**Stakeholders:** {', '.join(teams)}\n\n"
      f"**Executive summary:** {analysis.executive_summary[:600]}\n"
    )
    self._comments.add_comment(work_id=work_id, body=body)

    child_tasks = []
    war_actions = [
      ("Executive briefing draft", "Compliance"),
      ("Impact assessment sign-off", routing.primary_team if routing else "Compliance"),
      ("SLA monitoring setup", "Compliance"),
    ]
    for title, team in war_actions:
      task = self._tasks.create_issue(
        title=f"[War Room] {title} — {display_id}",
        body=f"Parent coordination: {display_id}\nTeam: {team}\nTrace: {trace_id}",
        tags=["war-room", "regops"],
      )
      if task:
        child_tasks.append(task.get("id"))

    self._advanced.set_stage(work_id, stage_hint="in_progress")

    escalation = EscalationRecord(
      notification_id=notification_id or 0,
      escalation_level=analysis.priority.lower(),
      reason=analysis.compliance_risk[:1000],
      teams_notified=json.dumps(teams),
      devrev_work_id=work_id,
      status="active",
    )
    self._db.add(escalation)

    wf = WorkflowState(
      notification_id=notification_id or 0,
      workflow_type="war_room",
      current_stage="active",
      assigned_teams=json.dumps(teams),
      devrev_parent_work_id=work_id,
      metadata_json=json.dumps({"child_tasks": child_tasks, "trace_id": trace_id}),
    )
    self._db.add(wf)
    self._db.commit()

    logger.info("war_room_activated", work_id=work_id, child_tasks=len(child_tasks))
    return {
      "activated": True,
      "work_id": work_id,
      "child_tasks": child_tasks,
      "teams": teams,
    }
