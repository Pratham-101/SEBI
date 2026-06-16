"""Extract machine-readable obligations from regulatory analysis."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.obligation import Obligation
from app.sla.engine import SlaEngine
from app.schemas.analysis import ActionableInsight, RegulatoryAnalysisOutput


_OBLIGATION_PATTERNS = [
  (r"\breport\b", "mandatory_reporting"),
  (r"\bdisclos", "disclosure"),
  (r"\baudit\b", "audit_requirement"),
  (r"\bkyc\b", "kyc_obligation"),
  (r"\bdeadline\b|\bdue\b|\bwithin \d+", "deadline"),
  (r"\bundertaking\b|\bconfidential", "confidentiality_undertaking"),
  (r"\bcomply\b|\bcompliance\b", "compliance_action"),
]


class ObligationExtractor:
  def __init__(self, db: Session) -> None:
    self._db = db
    self._sla = SlaEngine(db)

  def _classify(self, text: str) -> str:
    lower = text.lower()
    for pattern, otype in _OBLIGATION_PATTERNS:
      if re.search(pattern, lower):
        return otype
    return "general_obligation"

  def extract_and_persist(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    analysis: RegulatoryAnalysisOutput,
  ) -> list[Obligation]:
    created: list[Obligation] = []

    for insight in analysis.actionable_insights:
      created.append(
        self._create(
          notification_id=notification_id,
          regulator_code=regulator_code,
          text=insight.action,
          owner_team=insight.owner_team,
          source_basis=insight.dependencies or "actionable_insight",
          urgency=insight.urgency,
        )
      )

    for deadline in analysis.deadlines:
      created.append(
        self._create(
          notification_id=notification_id,
          regulator_code=regulator_code,
          text=deadline,
          owner_team=analysis.suggested_owner_team,
          source_basis="deadline",
          obligation_type="deadline",
        )
      )

    for date in analysis.important_dates:
      created.append(
        self._create(
          notification_id=notification_id,
          regulator_code=regulator_code,
          text=f"{date.label}: {date.date_text}",
          owner_team=analysis.suggested_owner_team,
          source_basis=date.source_basis or "important_date",
          obligation_type="deadline",
          deadline_text=date.date_text,
        )
      )

    self._db.commit()
    return created

  def _create(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    text: str,
    owner_team: str,
    source_basis: str,
    obligation_type: str | None = None,
    deadline_text: str | None = None,
    urgency: str = "standard",
  ) -> Obligation:
    otype = obligation_type or self._classify(text)
    risk = "high" if urgency in ("immediate", "urgent", "critical") else "medium"
    ob = Obligation(
      notification_id=notification_id,
      regulator_code=regulator_code,
      obligation_type=otype,
      description=text[:2000],
      owner_team=owner_team[:64],
      deadline_text=deadline_text,
      status="detected",
      risk_level=risk,
      source_basis=source_basis[:500],
    )
    self._db.add(ob)
    self._db.flush()
    self._sla.initialize(ob)
    return ob
