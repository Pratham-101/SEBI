"""Regulatory Ingestion Agent — multi-regulator scrape and enrich."""

from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.domain.regulators.registry import get_regulator
from app.models.notification import Notification
from app.services.dedup.engine import DeduplicationEngine


class IngestionAgent(BaseAgent):
  name = "regulatory_ingestion"

  def run(self, ctx: RegOpsContext) -> RegOpsContext:
    plugin = get_regulator(ctx.regulator_code)
    item = ctx.item
    dedup = DeduplicationEngine(self._db)
    item = dedup.enrich_hashes(item)
    existing = dedup.is_duplicate(item)

    if existing:
      if existing.processing_state not in (
        "extracted",
        "failed",
        "pending_human_review",
        "analyzed",
      ):
        ctx.stats["skipped_duplicate"] = ctx.stats.get("skipped_duplicate", 0) + 1
        return ctx
      ctx.notification_id = existing.id
      if not existing.body_text and item.body_text:
        existing.body_text = item.body_text
        existing.content_hash = item.content_hash
        self._db.commit()
      ctx.item = item.model_copy(
        update={
          "title": existing.title,
          "body_text": existing.body_text or item.body_text,
          "url_hash": existing.url_hash,
          "content_hash": existing.content_hash,
          "regulator_code": existing.regulator_code or ctx.regulator_code,
        }
      )
      return ctx

    item = plugin.enrich_content(item)
    notification = Notification(
      title=item.title,
      url=item.url,
      url_hash=item.url_hash,
      content_hash=item.content_hash,
      regulator_code=ctx.regulator_code,
      notification_type=item.notification_type,
      published_date=item.published_date,
      body_text=item.body_text,
      pdf_urls=json.dumps(item.pdf_urls),
      processing_state="extracted",
    )
    self._db.add(notification)
    self._db.commit()
    self._db.refresh(notification)
    ctx.notification_id = notification.id
    ctx.item = item
    from app.events.emitter import IntelligenceEmitter

    IntelligenceEmitter(self._db).emit(
      event_type="regulation_detected",
      title="New regulation detected",
      narrative=item.title[:200],
      severity="info",
      regulator_code=ctx.regulator_code,
      notification_id=notification.id,
      trace_id=ctx.trace_id,
    )
    return ctx
