"""Applicability Agent — relevance gate before expensive AI classification.

Scores whether a freshly ingested SEBI item applies to the org. If it scores
below the configured threshold, the pipeline stops here: the notification is
marked `not_applicable` and no analysis/ticket is produced — cutting noise and
LLM spend on items that don't concern us.
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.context import RegOpsContext
from app.models.notification import Notification
from app.services.routing.applicability import ApplicabilityEngine


class ApplicabilityAgent(BaseAgent):
    name = "applicability"

    def __init__(self, db) -> None:
        super().__init__(db)
        self._engine = ApplicabilityEngine()

    def run(self, ctx: RegOpsContext) -> RegOpsContext:
        if not ctx.notification_id:
            return ctx

        result = self._engine.score(
            title=ctx.item.title,
            body_text=ctx.item.body_text or "",
            notification_type=ctx.item.notification_type,
        )
        ctx.applicability_score = result.score
        ctx.applicable = result.applicable
        ctx.intel_metadata["applicability"] = {
            "score": result.score,
            "matched": result.matched,
            "excluded_by": result.excluded_by,
            "rationale": result.rationale,
        }

        if not result.applicable:
            ctx.not_applicable_reason = result.rationale
            # Signal the coordinator to stop processing this item.
            ctx.stats["not_applicable"] = ctx.stats.get("not_applicable", 0) + 1
            notification = self._db.get(Notification, ctx.notification_id)
            if notification:
                notification.processing_state = "not_applicable"
                self._db.commit()

            from app.events.emitter import IntelligenceEmitter

            IntelligenceEmitter(self._db).emit(
                event_type="regulation_filtered",
                title="Filtered as not applicable",
                narrative=f"{ctx.item.title[:140]} — {result.rationale}",
                severity="info",
                regulator_code=ctx.regulator_code,
                notification_id=ctx.notification_id,
                trace_id=ctx.trace_id,
            )

        return ctx
