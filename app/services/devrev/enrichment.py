"""Post-create DevRev enrichment: child insight tickets."""

from __future__ import annotations

import structlog

from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.devrev.comments import DevRevCommentService
from app.services.devrev.mapping import collect_tag_names
from app.services.devrev.tasks import DevRevTaskService
from app.services.devrev.tickets import DevRevTicketService
from app.services.routing.team_router import RoutingDecision

logger = structlog.get_logger(__name__)


class DevRevEnrichmentService:
    """Apply operational workflow automation after ticket creation."""

    def __init__(self) -> None:
        self._comments = DevRevCommentService()
        self._tasks = DevRevTaskService()
        self._tickets = DevRevTicketService()

    def enrich_ticket(
        self,
        *,
        work_id: str,
        display_id: str,
        analysis: RegulatoryAnalysisOutput,
        routing: RoutingDecision,
        escalation_note: str,
        related: list[dict],
        source_url: str,
        notification_type: str,
        published_date: str | None = None,
        group_id: str | None = None,
        assignment=None,
        assignment_engine=None,
    ) -> dict:
        results: dict = {"subtasks": [], "linked": 0, "comment": None}

        owner_line = ""
        if assignment is not None and getattr(assignment, "user_id", None):
            owner_line = f"- Assigned owner: **{assignment.display_name}**\n"

        routing_comment = (
            f"**Regulatory Operations Routing**\n\n"
            f"- Primary group: **{routing.devrev_group_name}**\n"
            f"- Primary team: **{routing.primary_team}**\n"
            f"{owner_line}"
            f"- Severity: **{routing.severity}**\n"
            f"- Notify teams (tags): "
            f"{', '.join(f'team:{s}' for s in _notify_team_slugs(routing)) or 'none'}\n"
        )
        if assignment is not None and getattr(assignment, "rationale", None) and getattr(
            assignment, "user_id", None
        ):
            routing_comment += f"\n_Why this owner:_ {assignment.rationale}\n"
        if escalation_note:
            routing_comment += f"\n{escalation_note}\n"

        if related:
            routing_comment += "\n**Related prior notifications:**\n"
            for r in related[:3]:
                title = r.get("title") or "Related notification"
                routing_comment += f"- {title}\n"

        results["comment"] = self._comments.add_comment(
            work_id=work_id, body=routing_comment
        )

        parent_tag_names = collect_tag_names(analysis, routing=routing)
        if analysis.actionable_insights:
            subtask_result = self._tasks.create_subtasks(
                parent_work_id=work_id,
                parent_display_id=display_id,
                analysis=analysis,
                parent_tag_names=parent_tag_names,
                group_id=group_id,
                published_date=published_date,
                assignment_engine=assignment_engine,
            )
            results["subtasks"] = subtask_result.get("children", [])
            results["linked"] = subtask_result.get("linked", 0)

        # DevRev tenant snap-in rewrites parent body when child issues are created.
        self._tickets.restore_lean_body(
            work_id=work_id,
            analysis=analysis,
            source_url=source_url,
            notification_type=notification_type,
            published_date=published_date,
        )

        logger.info(
            "devrev_enrichment_complete",
            work_id=work_id,
            subtasks=len(results["subtasks"]),
            child_issues_linked=results["linked"],
        )
        return results


def _notify_team_slugs(routing: RoutingDecision) -> list[str]:
    from app.services.routing.team_router import team_to_tag_slug

    primary = team_to_tag_slug(routing.primary_team)
    slugs: list[str] = []
    for team in routing.teams_to_notify:
        slug = team_to_tag_slug(team)
        if slug != primary and slug not in slugs:
            slugs.append(slug)
    return slugs
