"""Organizational memory persistence."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.organizational_memory import OrganizationalMemory
from app.schemas.analysis import RegulatoryAnalysisOutput


class MemoryStore:
  def __init__(self, db: Session) -> None:
    self._db = db

  def record_from_analysis(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    analysis: RegulatoryAnalysisOutput,
    outcome: str = "processed",
  ) -> None:
    themes = analysis.related_themes or [analysis.regulatory_domain]
    for theme in themes[:5]:
      entry = OrganizationalMemory(
        memory_type="regulatory_response",
        regulator_code=regulator_code,
        theme=theme[:128],
        summary=(
          f"{analysis.ticket_title}: {analysis.executive_summary[:500]}"
        ),
        notification_id=notification_id,
        outcome=outcome,
        confidence=analysis.confidence_score,
        embedding_key=f"{regulator_code}:{theme}".lower().replace(" ", "_"),
      )
      self._db.add(entry)

    if analysis.priority in ("HIGH", "CRITICAL"):
      gap = OrganizationalMemory(
        memory_type="risk_signal",
        regulator_code=regulator_code,
        theme=analysis.regulatory_domain[:128],
        summary=analysis.compliance_risk[:800],
        notification_id=notification_id,
        outcome="elevated",
        confidence=analysis.confidence_score,
      )
      self._db.add(gap)

    self._db.commit()
    self._index_vectors()

  def _index_vectors(self) -> None:
    try:
      from app.memory.vector import VectorMemoryService

      rows = (
        self._db.query(OrganizationalMemory)
        .order_by(OrganizationalMemory.id.desc())
        .limit(20)
        .all()
      )
      vec = VectorMemoryService(self._db)
      for row in rows:
        vec.index_memory(row)
    except Exception:
      pass

  def record_workflow_outcome(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    memory_type: str,
    theme: str,
    summary: str,
    outcome: str,
    related_ids: list[int] | None = None,
  ) -> None:
    entry = OrganizationalMemory(
      memory_type=memory_type,
      regulator_code=regulator_code,
      theme=theme[:128],
      summary=summary,
      notification_id=notification_id,
      related_notification_ids=json.dumps(related_ids or []),
      outcome=outcome,
    )
    self._db.add(entry)
    self._db.commit()
