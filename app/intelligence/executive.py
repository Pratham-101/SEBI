"""Executive intelligence engine — strategic compliance analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.escalation_record import EscalationRecord
from app.models.notification import Notification
from app.models.obligation import Obligation
from app.models.organizational_memory import OrganizationalMemory


class ExecutiveIntelligenceEngine:
    def __init__(self, db: Session) -> None:
        self._db = db

    def generate(self, *, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        notifications = (
            self._db.query(Notification)
            .filter(Notification.created_at >= since)
            .all()
        )
        by_regulator: dict[str, int] = {}
        for n in notifications:
            code = getattr(n, "regulator_code", None) or "SEBI"
            by_regulator[code] = by_regulator.get(code, 0) + 1

        high_critical = (
            self._db.query(AnalysisResult)
            .filter(
                AnalysisResult.created_at >= since,
                AnalysisResult.priority.in_(("HIGH", "CRITICAL")),
            )
            .count()
        )
        open_obligations = (
            self._db.query(Obligation)
            .filter(Obligation.status.notin_(("completed", "validated")))
            .count()
        )
        failed_memory = (
            self._db.query(OrganizationalMemory)
            .filter(OrganizationalMemory.outcome.in_(("failed", "delayed", "elevated")))
            .count()
        )
        active_escalations = (
            self._db.query(EscalationRecord)
            .filter(EscalationRecord.status == "active")
            .count()
        )

        team_load = (
            self._db.query(Obligation.owner_team, func.count(Obligation.id))
            .filter(Obligation.status.notin_(("completed",)))
            .group_by(Obligation.owner_team)
            .all()
        )

        total = max(len(notifications), 1)
        aggressiveness = min(1.0, (high_critical / total) * 2)

        return {
            "period_days": days,
            "regulator_aggressiveness_index": round(aggressiveness, 3),
            "compliance_debt_indicators": {
                "open_obligations": open_obligations,
                "failed_workflows": failed_memory,
                "active_escalations": active_escalations,
            },
            "recurring_operational_failures": self._recurring_themes(),
            "overloaded_teams": [{"team": t, "load": c} for t, c in team_load if c >= 5],
            "unresolved_critical_risks": high_critical,
            "trend_acceleration": self._trend_acceleration(since),
            "enforcement_heatmap": by_regulator,
            "notifications_by_regulator": by_regulator,
        }

    def _recurring_themes(self) -> list[dict]:
        rows = (
            self._db.query(OrganizationalMemory.theme, func.count(OrganizationalMemory.id))
            .filter(OrganizationalMemory.outcome.in_(("failed", "delayed", "elevated")))
            .group_by(OrganizationalMemory.theme)
            .order_by(func.count(OrganizationalMemory.id).desc())
            .limit(8)
            .all()
        )
        return [{"theme": t, "count": c} for t, c in rows]

    def _trend_acceleration(self, since: datetime) -> dict:
        mid = since + (datetime.now(timezone.utc) - since) / 2
        first_half = (
            self._db.query(Notification).filter(Notification.created_at < mid).count()
        )
        second_half = (
            self._db.query(Notification).filter(Notification.created_at >= mid).count()
        )
        rate = (second_half - first_half) / max(first_half, 1)
        return {"first_half": first_half, "second_half": second_half, "acceleration": round(rate, 3)}
