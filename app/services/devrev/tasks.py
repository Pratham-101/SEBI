"""Auto-generate linked DevRev child work items for actionable insights."""

from __future__ import annotations

import time

import structlog

from app.core.config import get_settings
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.devrev.client import DevRevClient
from app.services.devrev.links import DevRevLinkService, LINK_ATTEMPT_DELAY_SECONDS
from app.services.devrev.mapping import build_insight_child_body, collect_insight_tag_names
from app.services.devrev.tags import DevRevTagService
from app.services.routing.team_router import normalize_team, team_to_tag_slug
from app.services.scraper.date_resolver import compute_sla_due_date

logger = structlog.get_logger(__name__)


def _insight_title(action: str, *, max_len: int = 200) -> str:
    text = " ".join(action.split())
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 3].rsplit(" ", 1)[0]
    return f"{cut}..."


class DevRevTaskService:
    """Create child work items linked to the parent regulatory ticket."""

    def __init__(self, client: DevRevClient | None = None) -> None:
        self._client = client or DevRevClient()
        self._settings = get_settings()
        self._tags = DevRevTagService(self._client)
        self._links = DevRevLinkService(self._client)

    def create_subtasks(
        self,
        *,
        parent_work_id: str,
        parent_display_id: str,
        analysis: RegulatoryAnalysisOutput,
        parent_tag_names: list[str] | None = None,
        group_id: str | None = None,
        published_date: str | None = None,
        assignment_engine=None,
    ) -> dict:
        del group_id  # group is not supported on issue work items in this org

        part_id = self._settings.devrev_default_part_id
        if not part_id:
            logger.warning("devrev_subtasks_skipped", reason="missing_part_id")
            return {"children": [], "linked": 0}

        created: list[dict] = []
        linked = 0
        parent_tags = parent_tag_names or []
        insights = analysis.actionable_insights

        child_due_date = self._child_due_date(analysis, published_date)

        for idx, insight in enumerate(insights, start=1):
            title = _insight_title(insight.action)
            owner_team = normalize_team(insight.owner_team)

            # Resolve the individual owner for this specific action item.
            child_owner_id = None
            child_owner_name = None
            if assignment_engine is not None:
                decision = assignment_engine.assign(
                    analysis=analysis, team=owner_team
                )
                child_owner_id = decision.user_id
                child_owner_name = decision.display_name

            body = build_insight_child_body(
                insight=insight,
                parent_display_id=parent_display_id,
                published_date=published_date,
                assignee_name=child_owner_name,
                due_date=child_due_date,
            )
            tag_names = collect_insight_tag_names(
                analysis,
                parent_tag_names=parent_tags,
                owner_team=insight.owner_team,
            )

            payload: dict = {
                "type": "issue",
                "title": title[:240],
                "body": body,
                "applies_to_part": part_id,
                "external_ref": f"sebi-sub:{parent_work_id}:{idx}",
                "tags": self._tags.resolve_tag_ids(tag_names),
            }
            owner_id = child_owner_id or self._settings.devrev_default_owner_id
            if owner_id:
                payload["owned_by"] = [owner_id]
            if self._settings.devrev_send_due_dates and child_due_date:
                payload[self._settings.devrev_due_date_field] = child_due_date

            try:
                response = self._client.post("works.create", json_body=payload)
                work = response.get("work", response)
                child_id = work.get("id")
                if child_id:
                    time.sleep(LINK_ATTEMPT_DELAY_SECONDS)
                    if self._links.link_parent_child(
                        parent_work_id=parent_work_id,
                        child_work_id=child_id,
                    ):
                        linked += 1
                created.append(work)
                logger.info(
                    "devrev_insight_child_created",
                    parent=parent_display_id,
                    child=work.get("display_id"),
                    owner_team=owner_team,
                    assignee=child_owner_name,
                    team_tag=f"team:{team_to_tag_slug(owner_team)}",
                )
            except Exception as exc:
                logger.error("devrev_insight_child_failed", index=idx, error=str(exc))

        logger.info(
            "child_issues_summary",
            parent=parent_display_id,
            child_issues_created=len(created),
            child_issues_linked=linked,
        )
        return {"children": created, "linked": linked}

    def _child_due_date(
        self, analysis: RegulatoryAnalysisOutput, published_date: str | None
    ) -> str | None:
        """Due date for child action items, derived from the earliest deadline."""
        deadline_text = None
        if analysis.important_dates:
            deadline_text = analysis.important_dates[0].date_text
        return compute_sla_due_date(
            deadline_text=deadline_text,
            published_date=published_date,
            priority=analysis.priority,
            lead_days_critical=self._settings.devrev_sla_lead_days_critical,
            lead_days_high=self._settings.devrev_sla_lead_days_high,
            lead_days_default=self._settings.devrev_sla_lead_days_default,
        )

    def create_issue(
        self,
        *,
        title: str,
        body: str,
        tags: list[str] | None = None,
        group_id: str | None = None,
    ) -> dict | None:
        part_id = self._settings.devrev_default_part_id
        if not part_id:
            return None

        payload: dict = {
            "type": "issue",
            "title": title[:240],
            "body": body,
            "applies_to_part": part_id,
        }
        if group_id:
            payload["group"] = group_id
        if tags:
            payload["tags"] = self._tags.resolve_tag_ids(tags)
        if self._settings.devrev_default_owner_id:
            payload["owned_by"] = [self._settings.devrev_default_owner_id]

        try:
            response = self._client.post("works.create", json_body=payload)
            return response.get("work", response)
        except Exception as exc:
            logger.warning("devrev_issue_create_failed", error=str(exc))
            return None
