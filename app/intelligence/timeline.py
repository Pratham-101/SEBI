"""Live intelligence timeline."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.intelligence_event import IntelligenceEvent


class IntelligenceTimeline:
    def __init__(self, db: Session) -> None:
        self._db = db

    def recent(self, *, limit: int = 100, event_type: str | None = None) -> list[dict]:
        q = self._db.query(IntelligenceEvent).order_by(IntelligenceEvent.created_at.desc())
        if event_type:
            q = q.filter(IntelligenceEvent.event_type == event_type)
        rows = q.limit(limit).all()
        return [self._serialize(r) for r in rows]

    def for_notification(self, notification_id: int) -> list[dict]:
        rows = (
            self._db.query(IntelligenceEvent)
            .filter(IntelligenceEvent.notification_id == notification_id)
            .order_by(IntelligenceEvent.created_at.asc())
            .all()
        )
        return [self._serialize(r) for r in rows]

    def _serialize(self, row: IntelligenceEvent) -> dict:
        import json

        return {
            "id": row.id,
            "event_type": row.event_type,
            "severity": row.severity,
            "title": row.title,
            "narrative": row.narrative,
            "regulator_code": row.regulator_code,
            "notification_id": row.notification_id,
            "trace_id": row.trace_id,
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "payload": json.loads(row.payload_json or "{}"),
        }
