"""Human-AI collaboration — proposals and decisions."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.memory.store import MemoryStore
from app.models.human_decision import HumanDecision


class CollaborationService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._memory = MemoryStore(db)

    def propose(
        self,
        *,
        notification_id: int,
        proposal_type: str,
        proposal: dict,
    ) -> dict:
        row = HumanDecision(
            notification_id=notification_id,
            proposal_type=proposal_type,
            proposal_json=json.dumps(proposal),
            decision="pending",
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._serialize(row)

    def decide(
        self,
        decision_id: int,
        *,
        decision: str,
        notes: str | None = None,
        decided_by: str = "operator",
    ) -> dict | None:
        if decision not in ("approved", "rejected", "modified"):
            raise ValueError("decision must be approved, rejected, or modified")

        row = self._db.get(HumanDecision, decision_id)
        if not row:
            return None

        row.decision = decision
        row.modifier_notes = notes
        row.decided_by = decided_by
        self._db.commit()

        if row.notification_id and decision in ("approved", "modified"):
            proposal = json.loads(row.proposal_json)
            self._memory.record_workflow_outcome(
                notification_id=row.notification_id,
                regulator_code=proposal.get("regulator_code", "SEBI"),
                memory_type="human_decision",
                theme=row.proposal_type,
                summary=f"Human {decision}: {notes or proposal.get('summary', '')}"[:500],
                outcome=decision,
            )

        return self._serialize(row)

    def pending(self, limit: int = 20) -> list[dict]:
        rows = (
            self._db.query(HumanDecision)
            .filter(HumanDecision.decision == "pending")
            .order_by(HumanDecision.id.desc())
            .limit(limit)
            .all()
        )
        return [self._serialize(r) for r in rows]

    def _serialize(self, row: HumanDecision) -> dict:
        return {
            "id": row.id,
            "notification_id": row.notification_id,
            "obligation_id": row.obligation_id,
            "proposal_type": row.proposal_type,
            "proposal": json.loads(row.proposal_json),
            "decision": row.decision,
            "notes": row.modifier_notes,
            "decided_by": row.decided_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
