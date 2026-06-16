"""Risk Analysis Agent — routing, escalation, risk scoring."""

from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.models.analysis_result import AnalysisResult
from app.models.notification import Notification
from app.services.routing.assignment import AssignmentEngine
from app.services.routing.escalation import EscalationEngine
from app.services.routing.team_router import TeamRouter


class RiskAnalysisAgent(BaseAgent):
  name = "risk_analysis"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._router = TeamRouter()
    self._escalation = EscalationEngine()
    self._assignment = AssignmentEngine(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis or not ctx.notification_id:
      return ctx

    analysis = ctx.analysis
    ctx.escalation = self._escalation.plan(
      analysis, governance_reasons=ctx.governance_reasons
    )
    ctx.routing = self._router.route(
      analysis, title=ctx.item.title, body_text=ctx.item.body_text
    )
    ctx.assignment = self._assignment.assign(
      analysis=analysis, team=ctx.routing.primary_team
    )

    risk_score = min(
      1.0,
      analysis.confidence_score
      * (1.2 if analysis.priority in ("CRITICAL", "HIGH") else 1.0),
    )

    row = (
      self._db.query(AnalysisResult)
      .filter(AnalysisResult.notification_id == ctx.notification_id)
      .order_by(AnalysisResult.id.desc())
      .first()
    )
    if row:
      row.requires_human_review = ctx.escalation.requires_human_review
      row.teams_json = json.dumps(analysis.teams_to_notify)
      row.deadlines_json = json.dumps([d.model_dump() for d in analysis.important_dates])
      row.action_items_json = json.dumps(
        [i.model_dump() for i in analysis.actionable_insights]
      )
      row.risk_score = risk_score
      row.escalation_state = (
        "executive" if ctx.escalation.requires_executive else "standard"
      )
      row.routing_json = json.dumps(ctx.intel_metadata.get("routing", {}))

    notification = self._db.get(Notification, ctx.notification_id)
    if notification:
      notification.processing_state = (
        "pending_human_review"
        if ctx.escalation.requires_human_review
        else "analyzed"
      )
    self._db.commit()
    return ctx
