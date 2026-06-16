"""Organizational Memory Agent — historical reasoning context."""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.memory.retrieval import MemoryRetrieval
from app.memory.store import MemoryStore


class OrganizationalMemoryAgent(BaseAgent):
  name = "organizational_memory"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._retrieval = MemoryRetrieval(db)
    self._store = MemoryStore(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis:
      return ctx

    query = f"{ctx.item.title} {ctx.analysis.regulatory_domain} {' '.join(ctx.analysis.related_themes[:5])}"
    ctx.historical_memories = self._retrieval.find_similar(
      regulator_code=ctx.regulator_code,
      themes=ctx.analysis.related_themes,
      domain=ctx.analysis.regulatory_domain,
      query_text=query,
    )

    if ctx.historical_memories and ctx.analysis.inferences is not None:
      top = ctx.historical_memories[0]
      note = (
        f"Historical context: {top['historical_note']} "
        f"Prior summary: {top['summary'][:200]}"
      )
      if note not in ctx.analysis.inferences:
        ctx.analysis.inferences = list(ctx.analysis.inferences) + [note]

    return ctx

  def persist(self, ctx: RegOpsContext) -> None:
    if not ctx.analysis or not ctx.notification_id:
      return
    self._store.record_from_analysis(
      notification_id=ctx.notification_id,
      regulator_code=ctx.regulator_code,
      analysis=ctx.analysis,
      outcome="ticket_created" if ctx.devrev_work_id else "analyzed",
    )
