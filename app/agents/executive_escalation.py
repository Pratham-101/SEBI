"""Executive Escalation Agent — war room for HIGH/CRITICAL."""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.war_room.orchestrator import WarRoomOrchestrator


class ExecutiveEscalationAgent(BaseAgent):
  name = "executive_escalation"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._war_room = WarRoomOrchestrator(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis or not ctx.devrev_work_id:
      return ctx

    if ctx.analysis.priority not in ("HIGH", "CRITICAL"):
      return ctx

    ctx.war_room = self._war_room.activate(
      notification_id=ctx.notification_id,
      work_id=ctx.devrev_work_id,
      display_id=ctx.devrev_display_id,
      analysis=ctx.analysis,
      routing=ctx.routing,
      predictions=ctx.predictions,
      trace_id=ctx.trace_id,
    )
    if ctx.war_room.get("activated"):
      ctx.stats["war_rooms"] = ctx.stats.get("war_rooms", 0) + 1
    return ctx
