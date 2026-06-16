"""Explainability engine — reasoning chains and evidence."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.ai_explanation import AiExplanation
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.routing.escalation import EscalationPlan
from app.services.routing.team_router import RoutingDecision


class ExplainabilityEngine:
    def __init__(self, db: Session) -> None:
        self._db = db

    def explain_risk(
        self,
        *,
        notification_id: int,
        analysis: RegulatoryAnalysisOutput,
        predictions: dict,
        historical_memories: list[dict],
    ) -> dict:
        chain = [
            {
                "step": 1,
                "claim": f"Priority assigned: {analysis.priority}",
                "because": [
                    f"Confidence score: {analysis.confidence_score:.2f}",
                    f"Compliance risk: {analysis.compliance_risk[:200]}",
                    f"Operational risk: {analysis.operational_risk[:200]}",
                ],
            },
            {
                "step": 2,
                "claim": f"Operational exposure: {predictions.get('operational_exposure', 'n/a')}",
                "because": predictions.get("likely_impacted_systems", []),
            },
        ]
        if historical_memories:
            chain.append(
                {
                    "step": 3,
                    "claim": "Historical pattern detected",
                    "because": [m.get("historical_note", m.get("summary", ""))[:200] for m in historical_memories[:3]],
                }
            )

        evidence = {
            "facts_from_source": analysis.facts_from_source[:6],
            "inferences": analysis.inferences[:6],
            "key_changes": analysis.key_regulatory_changes[:5],
        }
        summary = (
            f"Risk {analysis.priority} driven by source facts, "
            f"confidence {analysis.confidence_score:.0%}, "
            f"and {len(historical_memories)} historical precedents."
        )
        return self._persist(
            notification_id=notification_id,
            decision_type="risk_assignment",
            chain=chain,
            evidence=evidence,
            confidence=analysis.confidence_score,
            summary=summary,
        )

    def explain_routing(
        self,
        *,
        notification_id: int,
        analysis: RegulatoryAnalysisOutput,
        routing: RoutingDecision,
    ) -> dict:
        chain = [
            {
                "step": 1,
                "claim": f"Primary team: {routing.primary_team}",
                "because": [f"AI suggested: {analysis.suggested_owner_team}", f"Severity: {routing.severity}"],
            },
            {
                "step": 2,
                "claim": f"Teams notified: {', '.join(routing.teams_to_notify)}",
                "because": analysis.affected_teams[:8],
            },
        ]
        from dataclasses import asdict

        evidence = {"routing_rules": asdict(routing)}
        return self._persist(
            notification_id=notification_id,
            decision_type="team_routing",
            chain=chain,
            evidence=evidence,
            confidence=analysis.confidence_score,
            summary=f"Routed to {routing.primary_team} based on domain {analysis.regulatory_domain}.",
        )

    def explain_escalation(
        self,
        *,
        notification_id: int,
        analysis: RegulatoryAnalysisOutput,
        escalation: EscalationPlan,
    ) -> dict:
        chain = [
            {
                "step": 1,
                "claim": "Escalation evaluated",
                "because": [
                    f"requires_executive: {escalation.requires_executive}",
                    f"requires_human_review: {escalation.requires_human_review}",
                    f"priority: {analysis.priority}",
                ],
            }
        ]
        if escalation.requires_executive:
            chain.append(
                {
                    "step": 2,
                    "claim": "Executive escalation triggered",
                    "because": [
                        analysis.requires_executive_escalation,
                        escalation.timeline_note,
                    ],
                }
            )
        return self._persist(
            notification_id=notification_id,
            decision_type="escalation",
            chain=chain,
            evidence={"escalation_plan": vars(escalation)},
            confidence=analysis.confidence_score,
            summary=escalation.timeline_note or "Standard escalation path.",
        )

    def get_for_notification(self, notification_id: int) -> list[dict]:
        rows = (
            self._db.query(AiExplanation)
            .filter(AiExplanation.notification_id == notification_id)
            .order_by(AiExplanation.id.desc())
            .all()
        )
        return [self._serialize(r) for r in rows]

    def _persist(
        self,
        *,
        notification_id: int,
        decision_type: str,
        chain: list,
        evidence: dict,
        confidence: float,
        summary: str,
    ) -> dict:
        row = AiExplanation(
            notification_id=notification_id,
            decision_type=decision_type,
            reasoning_chain_json=json.dumps(chain),
            evidence_json=json.dumps(evidence),
            confidence=confidence,
            summary=summary,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._serialize(row)

    def _serialize(self, row: AiExplanation) -> dict:
        return {
            "id": row.id,
            "notification_id": row.notification_id,
            "decision_type": row.decision_type,
            "reasoning_chain": json.loads(row.reasoning_chain_json),
            "evidence": json.loads(row.evidence_json),
            "confidence": row.confidence,
            "summary": row.summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
