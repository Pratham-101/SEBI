"""Emit intelligence events to DB + live stream."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.events.bus import EventBus
from app.models.intelligence_event import IntelligenceEvent


class IntelligenceEmitter:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._bus = EventBus.get()

    def emit(
        self,
        *,
        event_type: str,
        title: str,
        narrative: str,
        severity: str = "info",
        regulator_code: str | None = None,
        notification_id: int | None = None,
        trace_id: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        row = IntelligenceEvent(
            event_type=event_type,
            severity=severity,
            title=title[:256],
            narrative=narrative,
            regulator_code=regulator_code,
            notification_id=notification_id,
            payload_json=json.dumps(payload or {}),
            trace_id=trace_id,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)

        event = {
            "id": row.id,
            "event_type": event_type,
            "severity": severity,
            "title": title,
            "narrative": narrative,
            "regulator_code": regulator_code,
            "notification_id": notification_id,
            "trace_id": trace_id,
            "payload": payload or {},
            "timestamp": row.created_at.isoformat() if row.created_at else None,
        }
        self._bus.publish_sync(event)
        return event
