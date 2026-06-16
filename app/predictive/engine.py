"""Predictive compliance reasoning engine."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.memory.retrieval import MemoryRetrieval
from app.models.risk_propagation import RiskPropagation
from app.schemas.analysis import RegulatoryAnalysisOutput


class PredictiveComplianceEngine:
  def __init__(self, db: Session) -> None:
    self._db = db
    self._memory = MemoryRetrieval(db)

  def assess(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    analysis: RegulatoryAnalysisOutput,
    historical_memories: list[dict],
  ) -> dict:
    priority_weight = {
      "CRITICAL": 0.95,
      "HIGH": 0.8,
      "MEDIUM": 0.5,
      "LOW": 0.25,
    }.get(analysis.priority, 0.5)

    historical_factor = min(0.3, len(historical_memories) * 0.06)
    operational_exposure = min(
      1.0, priority_weight * analysis.confidence_score + historical_factor
    )
    escalation_probability = min(
      1.0,
      operational_exposure
      + (0.15 if analysis.requires_executive_escalation else 0)
      + (0.1 if analysis.requires_immediate_attention else 0),
    )

    impacted_systems = self._infer_systems(analysis)
    enforcement_risk = (
      "elevated"
      if analysis.priority in ("CRITICAL", "HIGH")
      or "enforcement" in analysis.regulatory_domain.lower()
      else "moderate"
    )

    for team in analysis.affected_teams[:8]:
      score = operational_exposure * (0.9 if team == analysis.suggested_owner_team else 0.7)
      self._db.add(
        RiskPropagation(
          notification_id=notification_id,
          team=team[:64],
          risk_score=round(score, 3),
          exposure_type="operational",
          rationale=analysis.operational_risk[:500],
        )
      )
    self._db.commit()

    recurring = [
      m["theme"]
      for m in historical_memories
      if m.get("outcome") in ("elevated", "delayed", "failed")
    ]

    return {
      "operational_exposure": round(operational_exposure, 3),
      "escalation_probability": round(escalation_probability, 3),
      "likely_impacted_systems": impacted_systems,
      "enforcement_risk": enforcement_risk,
      "recurring_compliance_patterns": recurring[:5],
      "historical_context_count": len(historical_memories),
    }

  def _infer_systems(self, analysis: RegulatoryAnalysisOutput) -> list[str]:
    text = " ".join(
      [
        analysis.regulatory_domain,
        analysis.operational_impact_analysis,
        " ".join(analysis.related_themes),
      ]
    ).lower()
    systems = []
    keywords = {
      "onboarding": "client_onboarding",
      "mutual fund": "mutual_fund_operations",
      "reporting": "regulatory_reporting",
      "kyc": "kyc_aml",
      "surveillance": "trade_surveillance",
      "disclosure": "disclosure_management",
    }
    for kw, sys in keywords.items():
      if kw in text:
        systems.append(sys)
    return systems or ["general_compliance"]
