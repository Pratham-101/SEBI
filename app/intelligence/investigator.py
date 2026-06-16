"""AI Investigative Mode — root-cause intelligence."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.explainability.engine import ExplainabilityEngine
from app.intelligence.timeline import IntelligenceTimeline
from app.memory.retrieval import MemoryRetrieval
from app.models.analysis_result import AnalysisResult
from app.models.escalation_record import EscalationRecord
from app.models.notification import Notification
from app.models.obligation import Obligation
from app.models.organizational_memory import OrganizationalMemory


class RegulatoryInvestigator:
    def __init__(self, db: Session) -> None:
        self._db = db

    def investigate(
        self,
        *,
        notification_id: int | None = None,
        query: str | None = None,
    ) -> dict:
        if notification_id:
            return self._investigate_notification(notification_id)
        return self._investigate_global(query or "risk escalation patterns")

    def _investigate_notification(self, notification_id: int) -> dict:
        n = self._db.get(Notification, notification_id)
        ar = (
            self._db.query(AnalysisResult)
            .filter(AnalysisResult.notification_id == notification_id)
            .order_by(AnalysisResult.id.desc())
            .first()
        )
        timeline = IntelligenceTimeline(self._db).for_notification(notification_id)
        explanations = ExplainabilityEngine(self._db).get_for_notification(notification_id)
        obligations = (
            self._db.query(Obligation)
            .filter(Obligation.notification_id == notification_id)
            .all()
        )
        escalations = (
            self._db.query(EscalationRecord)
            .filter(EscalationRecord.notification_id == notification_id)
            .all()
        )

        root_causes = []
        if ar and ar.priority in ("HIGH", "CRITICAL"):
            root_causes.append(
                {
                    "cause": "Elevated regulatory classification",
                    "evidence": f"Priority {ar.priority}, risk score {ar.risk_score}",
                }
            )
        overdue = [o for o in obligations if o.status == "overdue"]
        if overdue:
            root_causes.append(
                {
                    "cause": "SLA / obligation delays",
                    "evidence": f"{len(overdue)} overdue obligations",
                }
            )
        if escalations:
            root_causes.append(
                {
                    "cause": "Active escalation chain",
                    "evidence": [e.reason[:150] for e in escalations[:3]],
                }
            )

        memories = MemoryRetrieval(self._db).find_similar(
            regulator_code=getattr(n, "regulator_code", "SEBI") if n else "SEBI",
            themes=[],
            domain="",
            query_text=n.title if n else "",
            limit=5,
        )
        if memories:
            root_causes.append(
                {
                    "cause": "Historical pattern recurrence",
                    "evidence": [m.get("summary", "")[:120] for m in memories[:3]],
                }
            )

        return {
            "scope": "notification",
            "notification_id": notification_id,
            "title": n.title if n else "",
            "root_causes": root_causes,
            "timeline": timeline,
            "explanations": explanations,
            "recommendations": self._recommendations(root_causes),
            "report_summary": self._summarize(root_causes, n.title if n else ""),
        }

    def _investigate_global(self, query: str) -> dict:
        failed = (
            self._db.query(OrganizationalMemory)
            .filter(OrganizationalMemory.outcome.in_(("failed", "delayed", "elevated")))
            .order_by(OrganizationalMemory.created_at.desc())
            .limit(15)
            .all()
        )
        patterns: dict[str, int] = {}
        for m in failed:
            patterns[m.theme] = patterns.get(m.theme, 0) + 1

        recurring = sorted(patterns.items(), key=lambda x: -x[1])[:8]
        memories = MemoryRetrieval(self._db).find_similar(
            regulator_code="SEBI",
            themes=query.split()[:5],
            domain="",
            query_text=query,
            limit=10,
        )

        return {
            "scope": "global",
            "query": query,
            "recurring_patterns": [{"theme": t, "count": c} for t, c in recurring],
            "historical_signals": memories,
            "root_causes": [
                {"cause": "Recurring theme", "evidence": t}
                for t, c in recurring[:5]
            ],
            "report_summary": (
                f"Investigation identified {len(recurring)} recurring failure themes "
                f"and {len(memories)} semantically related historical signals."
            ),
        }

    def _recommendations(self, root_causes: list[dict]) -> list[str]:
        recs = []
        for rc in root_causes:
            if "SLA" in rc["cause"]:
                recs.append("Activate autonomous follow-up on overdue obligations.")
            if "escalation" in rc["cause"].lower():
                recs.append("Open executive war room review within 4 hours.")
            if "Historical" in rc["cause"]:
                recs.append("Apply institutional playbook from prior similar circular.")
        if not recs:
            recs.append("Continue standard monitoring; no critical root cause cluster.")
        return recs

    def _summarize(self, root_causes: list[dict], title: str) -> str:
        if not root_causes:
            return f"No dominant root causes for '{title}'."
        return (
            f"Investigation for '{title[:80]}' identified {len(root_causes)} "
            f"contributing factors: {', '.join(rc['cause'] for rc in root_causes)}."
        )
