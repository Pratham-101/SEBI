"""Compliance SLA engine — full obligation lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.obligation import Obligation
from app.models.obligation_event import OBLIGATION_STATES, ObligationEvent
from app.models.sla_tracking import SlaTracking


class SlaEngine:
    TRANSITIONS = {
        "detected": {"acknowledged", "assigned"},
        "acknowledged": {"assigned", "in_progress"},
        "assigned": {"in_progress", "overdue"},
        "in_progress": {"validated", "overdue", "escalated", "completed"},
        "overdue": {"escalated", "in_progress", "completed"},
        "escalated": {"in_progress", "completed"},
        "validated": {"completed"},
    }

    def __init__(self, db: Session) -> None:
        self._db = db

    def initialize(self, obligation: Obligation) -> None:
        obligation.status = "detected"
        self._record_event(obligation.id, None, "detected", "system", "Obligation detected")
        sla = SlaTracking(
            notification_id=obligation.notification_id,
            obligation_id=obligation.id,
            status="on_track",
        )
        self._db.add(sla)
        self._db.commit()

    def transition(
        self,
        obligation_id: int,
        to_status: str,
        *,
        actor: str = "system",
        notes: str | None = None,
    ) -> dict | None:
        if to_status not in OBLIGATION_STATES:
            raise ValueError(f"Invalid status: {to_status}")

        ob = self._db.get(Obligation, obligation_id)
        if not ob:
            return None

        allowed = self.TRANSITIONS.get(ob.status, set())
        if ob.status != to_status and to_status not in allowed and ob.status != "detected":
            if ob.status not in ("open", "in_progress"):
                pass
            elif to_status in ("assigned", "in_progress", "acknowledged"):
                pass
            elif allowed and to_status not in allowed:
                raise ValueError(f"Cannot transition {ob.status} -> {to_status}")

        from_status = ob.status
        ob.status = to_status
        ob.updated_at = datetime.now(timezone.utc)

        if to_status == "overdue":
            sla = self._get_sla(obligation_id)
            if sla:
                sla.status = "breached"
                sla.breached_at = datetime.now(timezone.utc)
        elif to_status == "completed":
            sla = self._get_sla(obligation_id)
            if sla:
                sla.status = "met"

        self._record_event(obligation_id, from_status, to_status, actor, notes)
        self._db.commit()
        return {"id": ob.id, "status": ob.status, "from": from_status}

    def scan_overdue(self) -> list[dict]:
        rows = (
            self._db.query(Obligation)
            .filter(Obligation.status.in_(("assigned", "in_progress", "acknowledged", "open")))
            .all()
        )
        overdue = []
        now = datetime.now(timezone.utc)
        for ob in rows:
            if ob.deadline_at and ob.deadline_at < now:
                try:
                    self.transition(ob.id, "overdue", notes="SLA deadline passed")
                    overdue.append({"id": ob.id, "team": ob.owner_team})
                except ValueError:
                    ob.status = "overdue"
                    self._db.commit()
                    overdue.append({"id": ob.id, "team": ob.owner_team})
        return overdue

    def dashboard(self) -> dict:
        by_status: dict[str, int] = {}
        for st in OBLIGATION_STATES:
            by_status[st] = (
                self._db.query(Obligation).filter(Obligation.status == st).count()
            )
        breaches = (
            self._db.query(SlaTracking).filter(SlaTracking.status == "breached").count()
        )
        return {"by_status": by_status, "sla_breaches": breaches}

    def _get_sla(self, obligation_id: int) -> SlaTracking | None:
        return (
            self._db.query(SlaTracking)
            .filter(SlaTracking.obligation_id == obligation_id)
            .first()
        )

    def _record_event(
        self, obligation_id: int, from_status: str | None, to_status: str, actor: str, notes: str | None
    ) -> None:
        self._db.add(
            ObligationEvent(
                obligation_id=obligation_id,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                notes=notes,
            )
        )
