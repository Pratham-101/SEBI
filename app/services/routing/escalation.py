"""Escalation workflows for human review and executive attention."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.routing.team_router import TEAM_EXECUTIVE, TEAM_LEGAL


@dataclass
class EscalationPlan:
    requires_human_review: bool
    requires_executive: bool
    assign_legal: bool
    extra_tags: list[str]
    timeline_note: str


class EscalationEngine:
    """Determine escalation actions after governance validation."""

    def plan(
        self,
        analysis: RegulatoryAnalysisOutput,
        *,
        governance_reasons: list[str],
    ) -> EscalationPlan:
        settings = get_settings()
        extra_tags: list[str] = []
        assign_legal = False
        timeline_parts: list[str] = []

        human_review = (
            analysis.confidence_score < settings.human_review_confidence_threshold
            or analysis.requires_immediate_attention
            or bool(governance_reasons)
        )

        if human_review:
            extra_tags.append("needs-human-review")
            assign_legal = True
            timeline_parts.append("Flagged for human review due to confidence or ambiguity.")

        executive = (
            analysis.requires_executive_escalation
            or analysis.priority in ("CRITICAL", "HIGH")
        )
        if executive:
            extra_tags.extend(["executive-attention", "urgent-review"])
            timeline_parts.append(f"Executive escalation: priority {analysis.priority}.")

        if analysis.priority == "CRITICAL":
            extra_tags.append("priority-critical")
            assign_legal = True

        if assign_legal and TEAM_LEGAL not in analysis.teams_to_notify:
            analysis.teams_to_notify.append(TEAM_LEGAL)

        if executive and TEAM_EXECUTIVE not in analysis.teams_to_notify:
            analysis.teams_to_notify.append(TEAM_EXECUTIVE)

        return EscalationPlan(
            requires_human_review=human_review,
            requires_executive=executive,
            assign_legal=assign_legal,
            extra_tags=extra_tags,
            timeline_note=" ".join(timeline_parts),
        )
