"""Strategic interpretation — Why This Matters."""

from __future__ import annotations

from app.schemas.analysis import RegulatoryAnalysisOutput


class StrategicInterpreter:
    def interpret(self, analysis: RegulatoryAnalysisOutput, *, regulator_code: str = "SEBI") -> dict:
        domain = analysis.regulatory_domain
        themes = analysis.related_themes[:5]

        significance = (
            f"This {regulator_code} action in '{domain}' signals active supervisory focus. "
            f"Priority {analysis.priority} indicates material operational impact for "
            f"{', '.join(analysis.affected_teams[:4])}."
        )

        direction = (
            "Regulatory direction points toward tighter governance and faster remediation cycles. "
            if analysis.priority in ("HIGH", "CRITICAL")
            else "Regulatory direction suggests routine compliance alignment with emerging guidance. "
        )

        market = (
            "Market implications include heightened investor disclosure expectations and "
            "potential sector-wide compliance reviews."
            if "mutual" in domain.lower() or "fund" in domain.lower()
            else "Market implications are moderate unless enforcement follow-up occurs."
        )

        governance = (
            f"Emerging themes: {', '.join(themes) if themes else 'general supervision'}. "
            f"Enforcement intensity correlates with {analysis.compliance_risk[:120]}."
        )

        return {
            "why_this_matters": significance,
            "strategic_significance": significance,
            "regulatory_direction": direction + governance,
            "market_implications": market,
            "governance_trends": governance,
            "emerging_enforcement_themes": themes,
            "executive_takeaway": analysis.executive_summary[:400],
        }
