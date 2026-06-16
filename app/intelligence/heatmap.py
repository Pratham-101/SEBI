"""Regulatory pressure heatmap data."""

from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.exposure.scoring import ExposureScoringEngine
from app.intelligence.executive import ExecutiveIntelligenceEngine
from app.models.analysis_result import AnalysisResult
from app.models.escalation_record import EscalationRecord
from app.models.notification import Notification
from app.models.obligation import Obligation


class PressureHeatmap:
    def __init__(self, db: Session) -> None:
        self._db = db

    def generate(self) -> dict:
        team_pressure = (
            self._db.query(
                Obligation.owner_team,
                func.count(Obligation.id).label("obligations"),
                func.sum(case((Obligation.status == "overdue", 1), else_=0)).label("overdue"),
            )
            .filter(Obligation.status.notin_(("completed", "validated")))
            .group_by(Obligation.owner_team)
            .all()
        )

        regulator_intensity = (
            self._db.query(
                Notification.regulator_code,
                func.count(Notification.id),
            )
            .group_by(Notification.regulator_code)
            .all()
        )

        enforcement = (
            self._db.query(AnalysisResult.priority, func.count(AnalysisResult.id))
            .filter(AnalysisResult.priority.in_(("HIGH", "CRITICAL")))
            .group_by(AnalysisResult.priority)
            .all()
        )

        escalations = (
            self._db.query(EscalationRecord.escalation_level, func.count(EscalationRecord.id))
            .filter(EscalationRecord.status == "active")
            .group_by(EscalationRecord.escalation_level)
            .all()
        )

        exposure = ExposureScoringEngine(self._db).enterprise_scores()
        executive = ExecutiveIntelligenceEngine(self._db).generate()

        max_ob = max((r.obligations for r in team_pressure), default=1) or 1
        cells = []
        for row in team_pressure:
            intensity = min(1.0, row.obligations / max_ob)
            if row.overdue:
                intensity = min(1.0, intensity + 0.3)
            cells.append(
                {
                    "team": row.owner_team,
                    "obligations": row.obligations,
                    "overdue": int(row.overdue or 0),
                    "intensity": round(intensity, 3),
                    "label": "critical" if intensity > 0.8 else "high" if intensity > 0.5 else "moderate",
                }
            )

        return {
            "team_pressure": cells,
            "regulator_aggressiveness": dict(regulator_intensity),
            "enforcement_intensity": dict(enforcement),
            "unresolved_escalations": dict(escalations),
            "compliance_exposure": exposure.get("compliance_exposure_score"),
            "obligation_density": sum(r.obligations for r in team_pressure),
            "regulator_aggressiveness_index": executive.get("regulator_aggressiveness_index"),
        }
