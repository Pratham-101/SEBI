"""Persist governance and pipeline audit events."""

from __future__ import annotations  # noqa: I001

import json

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        outcome: str,
        payload: dict | None = None,
        trace_id: str | None = None,
        actor: str = "system",
    ) -> AuditLog:
        entry = AuditLog(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            outcome=outcome,
            payload=json.dumps(payload) if payload else None,
            trace_id=trace_id,
        )
        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)
        return entry
