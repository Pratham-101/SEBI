"""Regulatory Knowledge Graph Agent."""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.knowledge.graph import KnowledgeGraphService


class KnowledgeGraphAgent(BaseAgent):
  name = "knowledge_graph"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._graph = KnowledgeGraphService(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis or not ctx.notification_id:
      return ctx

    related_ids = [r["id"] for r in ctx.related_notifications if r.get("id")]
    obligation_ids = [o["id"] for o in ctx.obligations]

    ctx.knowledge_graph = self._graph.build_from_analysis(
      notification_id=ctx.notification_id,
      regulator_code=ctx.regulator_code,
      title=ctx.item.title,
      analysis=ctx.analysis,
      devrev_work_id=ctx.devrev_work_id or None,
      related_ids=related_ids,
      obligation_ids=obligation_ids,
    )
    return ctx
