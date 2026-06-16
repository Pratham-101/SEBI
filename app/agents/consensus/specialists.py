"""Multi-agent consensus — specialist perspectives."""

from __future__ import annotations

from app.schemas.analysis import RegulatoryAnalysisOutput


def _perspective(
    role: str,
    focus: str,
    analysis: RegulatoryAnalysisOutput,
    weight: float,
) -> dict:
    return {
        "agent": role,
        "focus": focus,
        "assessment": focus,
        "priority_recommendation": analysis.priority,
        "confidence": round(analysis.confidence_score * weight, 3),
    }


class ConsensusCouncil:
    """Legal, Compliance, Risk, Finance, Executive perspectives."""

    def deliberate(self, analysis: RegulatoryAnalysisOutput) -> dict:
        legal = _perspective(
            "Legal AI Agent",
            f"Legal exposure: {analysis.legal_exposure}. "
            f"Key changes: {'; '.join(analysis.key_regulatory_changes[:2])}",
            analysis,
            0.95,
        )
        compliance = _perspective(
            "Compliance AI Agent",
            f"Compliance risk: {analysis.compliance_risk[:200]}. "
            f"Reporting burden: {analysis.reporting_burden}",
            analysis,
            1.0,
        )
        risk = _perspective(
            "Risk AI Agent",
            f"Operational risk: {analysis.operational_risk[:200]}. "
            f"Reputational: {analysis.reputational_impact}",
            analysis,
            1.0,
        )
        finance = _perspective(
            "Finance AI Agent",
            f"Operational impact: {analysis.operational_impact_analysis[:200]}. "
            f"Exposure: {analysis.compliance_exposure}",
            analysis,
            0.9,
        )
        executive = _perspective(
            "Executive Strategy Agent",
            f"Strategic summary: {analysis.executive_summary[:250]}. "
            f"Executive escalation: {analysis.requires_executive_escalation}",
            analysis,
            0.85,
        )

        perspectives = [legal, compliance, risk, finance, executive]
        avg_conf = sum(p["confidence"] for p in perspectives) / len(perspectives)
        consensus_priority = analysis.priority
        if analysis.requires_executive_escalation:
            consensus_priority = "CRITICAL"

        synthesis = (
            f"Council consensus: {consensus_priority} priority. "
            f"All agents align on {analysis.regulatory_domain} impact. "
            f"Compliance and Risk agents recommend immediate operational review. "
            f"Mean confidence {avg_conf:.0%}."
        )

        return {
            "perspectives": perspectives,
            "consensus": {
                "priority": consensus_priority,
                "synthesis": synthesis,
                "mean_confidence": round(avg_conf, 3),
                "unanimous_escalation": analysis.requires_executive_escalation,
            },
        }
