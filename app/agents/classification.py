"""Classification Agent — AI analysis and governance."""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.core.config import get_settings
from app.governance.validator import AIOutputValidator
from app.models.analysis_result import AnalysisResult
from app.services.ai.analyzer import RegulatoryAnalyzer
from app.services.intelligence.post_processor import IntelligencePostProcessor


class ClassificationAgent(BaseAgent):
  name = "classification"

  def __init__(self, db) -> None:
    super().__init__(db)
    self._analyzer = RegulatoryAnalyzer()
    self._governance = AIOutputValidator()
    self._post_processor = IntelligencePostProcessor()

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    if not ctx.notification_id:
      return ctx

    item = ctx.item
    analysis, raw = self._analyzer.analyze(
      title=item.title,
      notification_type=item.notification_type,
      source_url=item.url,
      body_text=item.body_text,
    )
    gov = self._governance.validate(analysis, source_text=item.body_text)
    analysis, intel_metadata = self._post_processor.enrich(
      analysis,
      title=item.title,
      body_text=item.body_text,
      governance_reasons=gov.reasons,
    )

    ctx.analysis = analysis
    ctx.raw_analysis = raw
    ctx.governance_approved = gov.approved
    ctx.governance_reasons = gov.reasons
    ctx.intel_metadata = intel_metadata

    row = AnalysisResult(
      notification_id=ctx.notification_id,
      model=get_settings().openai_model,
      raw_response=raw,
      structured_output=analysis.model_dump_json(),
      confidence_score=analysis.confidence_score,
      priority=analysis.priority,
      governance_status="approved" if gov.approved else "review",
      requires_human_review=False,
    )
    self._db.add(row)
    self._db.commit()
    return ctx
