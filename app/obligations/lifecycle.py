"""Obligation lifecycle management."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.obligation import Obligation
from app.models.sla_tracking import SlaTracking


class ObligationLifecycle:
  def __init__(self, db: Session) -> None:
    self._db = db

  def list_open(self, *, regulator_code: str | None = None, limit: int = 50) -> list[dict]:
    q = self._db.query(Obligation).filter(
      Obligation.status.in_(
        ("open", "in_progress", "detected", "acknowledged", "assigned", "overdue", "escalated")
      )
    )
    if regulator_code:
      q = q.filter(Obligation.regulator_code == regulator_code)
    rows = q.order_by(Obligation.created_at.desc()).limit(limit).all()
    return [self._serialize(r) for r in rows]

  def approaching_deadlines(self, days: int = 14) -> list[dict]:
    rows = (
      self._db.query(Obligation)
      .filter(Obligation.status == "open", Obligation.deadline_text.isnot(None))
      .limit(100)
      .all()
    )
    return [self._serialize(r) for r in rows]

  def update_status(self, obligation_id: int, status: str) -> dict | None:
    ob = self._db.get(Obligation, obligation_id)
    if not ob:
      return None
    ob.status = status
    ob.updated_at = datetime.now(timezone.utc)
    if status == "completed":
      sla = (
        self._db.query(SlaTracking)
        .filter(SlaTracking.obligation_id == obligation_id)
        .first()
      )
      if sla:
        sla.status = "met"
    self._db.commit()
    return self._serialize(ob)

  def _serialize(self, ob: Obligation) -> dict:
    return {
      "id": ob.id,
      "notification_id": ob.notification_id,
      "regulator_code": ob.regulator_code,
      "obligation_type": ob.obligation_type,
      "description": ob.description,
      "owner_team": ob.owner_team,
      "deadline_text": ob.deadline_text,
      "status": ob.status,
      "risk_level": ob.risk_level,
    }
