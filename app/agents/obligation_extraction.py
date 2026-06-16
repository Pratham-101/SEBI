"""Obligation Extraction Agent — structured compliance obligations."""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.obligations.extractor import ObligationExtractor


class ObligationExtractionAgent(BaseAgent):
  name = "obligation_extraction"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._extractor = ObligationExtractor(db)

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.analysis or not ctx.notification_id:
      return ctx

    obligations = self._extractor.extract_and_persist(
      notification_id=ctx.notification_id,
      regulator_code=ctx.regulator_code,
      analysis=ctx.analysis,
    )
    ctx.obligations = [
      {"id": o.id, "type": o.obligation_type, "team": o.owner_team, "status": o.status}
      for o in obligations
    ]
    return ctx
