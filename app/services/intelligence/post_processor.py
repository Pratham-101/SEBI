"""Post-process AI output with routing, tagging, and escalation."""

from __future__ import annotations

from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.routing.escalation import EscalationEngine
from app.services.routing.team_router import TeamRouter


class IntelligencePostProcessor:
    """Enrich analysis with routing decisions and operational tags."""

    def __init__(self) -> None:
        self._router = TeamRouter()
        self._escalation = EscalationEngine()

    def enrich(
        self,
        analysis: RegulatoryAnalysisOutput,
        *,
        title: str,
        body_text: str,
        governance_reasons: list[str],
    ) -> tuple[RegulatoryAnalysisOutput, dict]:
        routing = self._router.route(analysis, title=title, body_text=body_text)
        escalation = self._escalation.plan(analysis, governance_reasons=governance_reasons)

        analysis.suggested_owner_team = routing.primary_team
        analysis.teams_to_notify = list(
            dict.fromkeys(analysis.teams_to_notify + routing.teams_to_notify)
        )
        analysis.affected_teams = list(
            dict.fromkeys(analysis.affected_teams + routing.teams_to_notify)
        )

        base_tags = {
            "sebi-regulatory",
            f"priority-{analysis.priority.lower()}",
            analysis.regulatory_domain.replace(" ", "-").lower()[:40],
        }
        for tag in analysis.tags:
            base_tags.add(tag.strip().lower().replace(" ", "-"))

        if analysis.notification_type:
            base_tags.add(analysis.notification_type.replace("_", "-"))

        for theme in analysis.related_themes[:5]:
            base_tags.add(theme.replace(" ", "-").lower()[:30])

        for t in routing.escalation_tags + escalation.extra_tags:
            base_tags.add(t)

        if analysis.requires_immediate_attention:
            base_tags.add("urgent-review")

        analysis.tags = sorted(base_tags)

        metadata = {
            "routing": {
                "primary_team": routing.primary_team,
                "devrev_group_name": routing.devrev_group_name,
                "severity": routing.severity,
                "teams_to_notify": routing.teams_to_notify,
            },
            "escalation": {
                "requires_human_review": escalation.requires_human_review,
                "requires_executive": escalation.requires_executive,
                "assign_legal": escalation.assign_legal,
                "timeline_note": escalation.timeline_note,
            },
        }
        return analysis, metadata
