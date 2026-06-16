"""Predictive simulation — what happens if ignored?"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.analysis import RegulatoryAnalysisOutput


class SimulationEngine:
    def __init__(self, db: Session) -> None:
        self._db = db

    def simulate_ignored(
        self,
        *,
        analysis: RegulatoryAnalysisOutput,
        predictions: dict,
        days_ignored: int = 30,
    ) -> dict:
        base_exposure = float(predictions.get("operational_exposure", 0.5))
        escalation_prob = float(predictions.get("escalation_probability", 0.3))

        time_multiplier = 1 + (days_ignored / 30) * 0.5
        operational_impact = min(1.0, base_exposure * time_multiplier)
        enforcement_risk = (
            "critical"
            if analysis.priority == "CRITICAL"
            else "high"
            if analysis.priority == "HIGH"
            else "moderate"
        )
        if days_ignored > 14:
            enforcement_risk = "elevated" if enforcement_risk == "moderate" else enforcement_risk

        audit_exposure = min(1.0, operational_impact * 0.85 + escalation_prob * 0.15)
        workflow_delay_days = int(days_ignored * (1 + escalation_prob))
        compliance_delay_risk = min(1.0, (days_ignored / 60) + base_exposure * 0.3)

        downstream = predictions.get("likely_impacted_systems", ["general_compliance"])
        scenarios = [
            {
                "day": 7,
                "impact": round(operational_impact * 0.4, 2),
                "event": "Internal compliance gap widens; team backlog grows.",
            },
            {
                "day": 14,
                "impact": round(operational_impact * 0.65, 2),
                "event": "SLA breaches likely; regulator follow-up risk increases.",
            },
            {
                "day": days_ignored,
                "impact": round(operational_impact, 2),
                "event": "Executive escalation and audit scrutiny probable.",
            },
        ]

        return {
            "scenario": "ignored",
            "days_ignored": days_ignored,
            "operational_impact": round(operational_impact, 3),
            "enforcement_risk": enforcement_risk,
            "audit_exposure": round(audit_exposure, 3),
            "downstream_workflows": downstream,
            "estimated_delay_days": workflow_delay_days,
            "compliance_delay_risk": round(compliance_delay_risk, 3),
            "timeline": scenarios,
            "recommendation": (
                "Immediate war room activation and obligation assignment recommended."
                if operational_impact > 0.7
                else "Assign owner team and acknowledge obligations within 48h."
            ),
        }
