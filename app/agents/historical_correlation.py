"""Historical Correlation Agent — link to prior regulations."""

from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.models.analysis_result import AnalysisResult
from app.services.intelligence.relationships import RelationshipEngine


class HistoricalCorrelationAgent(BaseAgent):
  name = "historical_correlation"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._relationships = RelationshipEngine(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis or not ctx.notification_id:
      return ctx

    related = self._relationships.find_related(
      themes=ctx.analysis.related_themes,
      notification_type=ctx.item.notification_type,
      exclude_id=ctx.notification_id,
    )
    memory_related = [
      {
        "id": m.get("notification_id"),
        "title": m.get("title", ""),
        "source": "organizational_memory",
      }
      for m in ctx.historical_memories
      if m.get("notification_id")
    ]
    seen = {r.get("id") for r in related}
    for mr in memory_related:
      if mr.get("id") and mr["id"] not in seen:
        related.append(mr)
        seen.add(mr["id"])

    ctx.related_notifications = related

    row = (
      self._db.query(AnalysisResult)
      .filter(AnalysisResult.notification_id == ctx.notification_id)
      .order_by(AnalysisResult.id.desc())
      .first()
    )
    if row:
      row.related_json = json.dumps(related)
      self._db.commit()

    row_ids = [r["id"] for r in related if r.get("id")]
    if row_ids and ctx.analysis:
      correlation_note = (
        f"Correlates with {len(row_ids)} prior notification(s) "
        f"including themes: {', '.join(ctx.analysis.related_themes[:3])}"
      )
      ctx.intel_metadata["correlation"] = {
        "related_ids": row_ids,
        "note": correlation_note,
      }
    return ctx
