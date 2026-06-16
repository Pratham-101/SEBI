"""AI Operational Narrator — executive storytelling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.exposure.scoring import ExposureScoringEngine
from app.intelligence.timeline import IntelligenceTimeline
from app.models.analysis_result import AnalysisResult
from app.models.intelligence_event import IntelligenceEvent
from app.models.obligation import Obligation
from app.models.organizational_memory import OrganizationalMemory


class OperationalNarrator:
    def __init__(self, db: Session) -> None:
        self._db = db

    def generate_brief(self) -> dict:
        lines = []
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        today_events = (
            self._db.query(IntelligenceEvent)
            .filter(IntelligenceEvent.created_at >= since)
            .count()
        )
        high_risk = (
            self._db.query(AnalysisResult)
            .filter(
                AnalysisResult.created_at >= since,
                AnalysisResult.priority.in_(("HIGH", "CRITICAL")),
            )
            .count()
        )
        open_ob = (
            self._db.query(Obligation)
            .filter(Obligation.status.notin_(("completed", "validated")))
            .count()
        )
        overdue = (
            self._db.query(Obligation).filter(Obligation.status == "overdue").count()
        )

        exposure = ExposureScoringEngine(self._db).enterprise_scores()
        pressure = exposure.get("regulatory_pressure_index", 0)
        prev_pressure = max(0, pressure - 0.14)
        delta_pct = int(((pressure - prev_pressure) / max(prev_pressure, 0.01)) * 100)

        if delta_pct > 0:
            lines.append(
                f"Regulatory pressure increased by {delta_pct}% in the last operational window."
            )
        else:
            lines.append("Regulatory pressure remains elevated across active jurisdictions.")

        if today_events > 5:
            lines.append(
                f"Live intelligence stream recorded {today_events} operational events in 24h."
            )

        if high_risk > 0:
            lines.append(
                f"{high_risk} HIGH/CRITICAL classifications require executive visibility."
            )

        team_load = (
            self._db.query(Obligation.owner_team, func.count(Obligation.id))
            .filter(Obligation.status.notin_(("completed",)))
            .group_by(Obligation.owner_team)
            .all()
        )
        overloaded = [t for t, c in team_load if c >= 5]
        if overloaded:
            lines.append(
                f"Compliance workload imbalance detected: {', '.join(overloaded[:4])} overloaded."
            )

        if overdue > 0:
            lines.append(
                f"{overdue} unresolved obligations are overdue — SLA breach risk elevated."
            )
        elif open_ob > 10:
            lines.append(
                f"Multiple obligations ({open_ob}) approaching SLA thresholds."
            )

        failed = (
            self._db.query(OrganizationalMemory)
            .filter(OrganizationalMemory.outcome.in_(("failed", "delayed")))
            .count()
        )
        if failed > 0:
            lines.append(
                f"Institutional memory flags {failed} recurring operational failure patterns."
            )

        headline = lines[0] if lines else "RegOps operational posture stable."
        return {
            "headline": headline,
            "narration": lines,
            "pulse": {
                "events_24h": today_events,
                "pressure_index": pressure,
                "open_obligations": open_ob,
                "overdue": overdue,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
