"""Organizational exposure scoring."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.obligation import Obligation
from app.models.risk_propagation import RiskPropagation


class ExposureScoringEngine:
    def __init__(self, db: Session) -> None:
        self._db = db

    def enterprise_scores(self) -> dict:
        open_obligations = (
            self._db.query(Obligation)
            .filter(Obligation.status.notin_(("completed", "validated")))
            .count()
        )
        high_priority = (
            self._db.query(AnalysisResult)
            .filter(AnalysisResult.priority.in_(("HIGH", "CRITICAL")))
            .count()
        )
        avg_risk = (
            self._db.query(func.avg(RiskPropagation.risk_score)).scalar() or 0.0
        )

        compliance_exposure = min(1.0, open_obligations / 50 + float(avg_risk) * 0.4)
        regulatory_pressure = min(1.0, high_priority / 20)
        operational_risk = min(1.0, float(avg_risk) + open_obligations / 100)
        enforcement_probability = min(
            1.0, regulatory_pressure * 0.6 + compliance_exposure * 0.4
        )

        team_load = (
            self._db.query(RiskPropagation.team, func.avg(RiskPropagation.risk_score))
            .group_by(RiskPropagation.team)
            .all()
        )

        return {
            "compliance_exposure_score": round(compliance_exposure, 3),
            "regulatory_pressure_index": round(regulatory_pressure, 3),
            "operational_risk_score": round(operational_risk, 3),
            "enforcement_probability": round(enforcement_probability, 3),
            "team_risk_load": [
                {"team": t, "avg_risk": round(float(s), 3)} for t, s in team_load
            ],
        }
