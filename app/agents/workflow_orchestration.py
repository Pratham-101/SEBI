"""Workflow Orchestration Agent — DevRev command center."""

from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.core.config import get_settings
from app.governance.audit import AuditService
from app.models.historical_action import HistoricalAction
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.models.workflow_state import WorkflowState
from app.services.devrev.advanced import DevRevAdvancedService
from app.services.devrev.enrichment import DevRevEnrichmentService
from app.services.devrev.groups import DevRevGroupService
from app.services.devrev.tickets import DevRevTicketService


class WorkflowOrchestrationAgent(BaseAgent):
  name = "workflow_orchestration"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._devrev = DevRevTicketService()
    self._enrichment = DevRevEnrichmentService()
    self._advanced = DevRevAdvancedService()
    self._audit = AuditService(db)
    from app.services.routing.assignment import AssignmentEngine

    self._assignment_engine = AssignmentEngine(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis or not ctx.notification_id or not ctx.routing:
      return ctx

    external_ref = f"{ctx.regulator_code.lower()}:{ctx.item.url_hash}"
    if self._devrev.find_by_external_ref(external_ref):
      ctx.stats["skipped_duplicate"] = ctx.stats.get("skipped_duplicate", 0) + 1
      n = self._db.get(Notification, ctx.notification_id)
      if n:
        n.processing_state = "ticket_exists"
        self._db.commit()
      return ctx

    assignee_user_id = ctx.assignment.user_id if ctx.assignment else None
    assignee_name = ctx.assignment.display_name if ctx.assignment else None
    effective_date, compliance_deadline = self._derive_dates(ctx)
    response = self._devrev.create_regulatory_ticket(
      analysis=ctx.analysis,
      source_url=ctx.item.url,
      notification_type=ctx.item.notification_type,
      published_date=ctx.item.published_date,
      external_ref=external_ref,
      routing=ctx.routing,
      metadata={"trace_id": ctx.trace_id, **ctx.intel_metadata},
      related_notifications=ctx.related_notifications,
      assignee_user_id=assignee_user_id,
      assignee_name=assignee_name,
      applicability_score=ctx.applicability_score,
      effective_date=effective_date,
      compliance_deadline=compliance_deadline,
      obligation_count=len(ctx.obligations),
    )
    work = response.get("work", {})
    ctx.devrev_work_id = work.get("id", "")
    ctx.devrev_display_id = work.get("display_id", "")

    escalation_note = ctx.escalation.timeline_note if ctx.escalation else ""
    group_id = DevRevGroupService().resolve_group_id(ctx.routing.devrev_group_name)
    enrich = self._enrichment.enrich_ticket(
      work_id=ctx.devrev_work_id,
      display_id=ctx.devrev_display_id,
      analysis=ctx.analysis,
      routing=ctx.routing,
      escalation_note=escalation_note,
      related=ctx.related_notifications,
      source_url=ctx.item.url,
      notification_type=ctx.item.notification_type,
      published_date=ctx.item.published_date,
      group_id=group_id,
      assignment=ctx.assignment,
      assignment_engine=self._assignment_engine,
    )
    ctx.subtask_ids = [
      s.get("id") for s in enrich.get("subtasks", []) if s.get("id")
    ]

    self._advanced.apply_command_center(
      work_id=ctx.devrev_work_id,
      analysis=ctx.analysis,
      routing=ctx.routing,
      predictions=ctx.predictions,
      historical_memories=ctx.historical_memories,
    )

    wf = WorkflowState(
      notification_id=ctx.notification_id,
      workflow_type="regulatory_intake",
      current_stage="active",
      assigned_teams=json.dumps(ctx.routing.teams_to_notify),
      devrev_parent_work_id=ctx.devrev_work_id,
      metadata_json=json.dumps({"predictions": ctx.predictions}),
    )
    self._db.add(wf)

    ticket = Ticket(
      notification_id=ctx.notification_id,
      devrev_work_id=ctx.devrev_work_id,
      devrev_display_id=ctx.devrev_display_id,
      external_ref=external_ref,
      priority=ctx.analysis.priority,
      status="created",
      assigned_team=ctx.routing.primary_team,
      assignee_user_id=ctx.assignment.user_id if ctx.assignment else None,
      assignee_name=ctx.assignment.display_name if ctx.assignment else None,
      assignment_rationale=ctx.assignment.rationale if ctx.assignment else None,
      subtask_ids_json=json.dumps(ctx.subtask_ids),
    )
    self._db.add(ticket)

    self._notify_manager_if_critical(ctx)

    for insight in ctx.analysis.actionable_insights[:5]:
      self._db.add(
        HistoricalAction(
          notification_id=ctx.notification_id,
          action_type="planned",
          team=insight.owner_team,
          description=insight.action[:1000],
          status="open",
          devrev_work_id=ctx.devrev_work_id,
        )
      )

    n = self._db.get(Notification, ctx.notification_id)
    if n:
      n.processing_state = "ticket_created"
    self._db.commit()

    self._audit.log(
      event_type="devrev_ticket_created",
      entity_type="ticket",
      entity_id=ctx.devrev_work_id,
      outcome="success",
      payload={
        "display_id": ctx.devrev_display_id,
        "subtasks": len(ctx.subtask_ids),
        "regulator": ctx.regulator_code,
        "assignee": ctx.assignment.display_name if ctx.assignment else None,
        "assignee_user_id": ctx.assignment.user_id if ctx.assignment else None,
      },
      trace_id=ctx.trace_id,
    )
    ctx.stats["tickets_created"] = ctx.stats.get("tickets_created", 0) + 1
    ctx.stats["subtasks_created"] = ctx.stats.get("subtasks_created", 0) + len(
      ctx.subtask_ids
    )
    return ctx

  def _derive_dates(self, ctx: RegOpsContext) -> tuple[str | None, str | None]:
    """Pick (effective_date, compliance_deadline) from analysis important_dates.

    A date whose label mentions deadline/comply/file/submit is treated as the
    compliance deadline; the first effective/applicable date as the effective
    date. Falls back to the first available date for either slot.
    """
    if not ctx.analysis:
      return None, None
    effective = None
    deadline = None
    for d in ctx.analysis.important_dates:
      label = (d.label or "").lower()
      if deadline is None and any(
        k in label for k in ("deadline", "comply", "complian", "file", "submit", "due", "report")
      ):
        deadline = d.date_text
      if effective is None and any(
        k in label for k in ("effective", "applicab", "implement", "w.e.f", "commence")
      ):
        effective = d.date_text
    if ctx.analysis.important_dates:
      first = ctx.analysis.important_dates[0].date_text
      effective = effective or first
      deadline = deadline or first
    return effective, deadline

  def _notify_manager_if_critical(self, ctx: RegOpsContext) -> None:
    """On CRITICAL tickets, post a manager-escalation comment with the assignee."""
    settings = get_settings()
    if not settings.assignment_notify_manager_on_critical:
      return
    if not ctx.analysis or ctx.analysis.priority != "CRITICAL":
      return
    if not ctx.assignment or not ctx.assignment.manager_user_id:
      return

    owner = ctx.assignment.display_name or "the assigned owner"
    body = (
      f"**🚨 Critical regulatory escalation**\n\n"
      f"This CRITICAL item has been assigned to **{owner}** "
      f"({ctx.assignment.team}).\n\n"
      f"Manager visibility requested for SLA oversight.\n\n"
      f"_Assignment rationale:_ {ctx.assignment.rationale}"
    )
    try:
      from app.services.devrev.comments import DevRevCommentService

      DevRevCommentService().add_comment(work_id=ctx.devrev_work_id, body=body)
    except Exception:  # noqa: BLE001 — manager notify is best-effort
      pass
