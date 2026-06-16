"""DevRev ticket (work item) operations."""

from __future__ import annotations

from typing import Any

import structlog

from app.core.config import get_settings
from app.schemas.analysis import RegulatoryAnalysisOutput
from app.services.devrev.client import DevRevAPIError, DevRevClient
from app.services.devrev.groups import DevRevGroupService
from app.services.devrev.mapping import (
    build_custom_fields,
    build_ticket_body,
    collect_namespaced_tags,
    collect_tag_names,
    format_ticket_title,
    map_priority,
)
from app.services.scraper.date_resolver import compute_sla_due_date
from app.services.devrev.tags import DevRevTagService
from app.services.devrev.validators import (
    DevRevTicketCreateRequest,
    DevRevTicketUpdateRequest,
)
from app.services.routing.team_router import RoutingDecision

logger = structlog.get_logger(__name__)


class DevRevTicketService:
    """High-level ticket lifecycle for regulatory notifications."""

    def __init__(self, client: DevRevClient | None = None) -> None:
        self._client = client or DevRevClient()
        self._settings = get_settings()
        self._tags = DevRevTagService(self._client)
        self._groups = DevRevGroupService(self._client)

    def create_regulatory_ticket(
        self,
        *,
        analysis: RegulatoryAnalysisOutput,
        source_url: str,
        notification_type: str,
        published_date: str | None,
        external_ref: str,
        routing: RoutingDecision,
        metadata: dict | None = None,
        related_notifications: list[dict] | None = None,
        assignee_user_id: str | None = None,
        assignee_name: str | None = None,
        applicability_score: float | None = None,
        effective_date: str | None = None,
        compliance_deadline: str | None = None,
        obligation_count: int | None = None,
    ) -> dict[str, Any]:
        """Create a DevRev ticket from enriched AI analysis."""
        part_id = self._settings.devrev_default_part_id
        if not part_id:
            raise ValueError(
                "DEVREV_DEFAULT_PART_ID is required. Run scripts/verify_devrev.py to discover parts."
            )

        title = format_ticket_title(analysis, notification_date=published_date)
        body = build_ticket_body(
            analysis=analysis,
            source_url=source_url,
            notification_type=notification_type,
            published_date=published_date,
            metadata=metadata,
            related_notifications=related_notifications,
        )

        payload: dict[str, Any] = {
            "type": "ticket",
            "title": title,
            "body": body,
            "applies_to_part": part_id,
            "external_ref": external_ref,
            "severity": routing.severity,
        }

        group_id = self._groups.resolve_group_id(routing.devrev_group_name)
        if group_id:
            payload["group"] = group_id

        if self._settings.devrev_send_priority_field:
            payload["priority"] = map_priority(analysis.priority)

        # Compute the internal SLA due date from the regulatory deadline.
        sla_due_date = compute_sla_due_date(
            deadline_text=compliance_deadline or effective_date,
            published_date=published_date,
            priority=analysis.priority,
            lead_days_critical=self._settings.devrev_sla_lead_days_critical,
            lead_days_high=self._settings.devrev_sla_lead_days_high,
            lead_days_default=self._settings.devrev_sla_lead_days_default,
        )

        if self._settings.devrev_namespaced_tags:
            tag_names = collect_namespaced_tags(
                analysis,
                routing=routing,
                regulator_code=external_ref.split(":")[0].upper(),
                notification_type=notification_type,
                applicability_score=applicability_score,
                effective_date=effective_date,
                obligation_count=obligation_count,
            )
        else:
            tag_names = collect_tag_names(analysis, routing=routing)
        if tag_names:
            payload["tags"] = self._tags.resolve_tag_ids(tag_names)

        if self._settings.devrev_send_custom_fields:
            payload["custom_fields"] = build_custom_fields(
                analysis,
                regulator_code=external_ref.split(":")[0].upper(),
                effective_date=effective_date,
                compliance_deadline=compliance_deadline,
                sla_due_date=sla_due_date,
                applicability_score=applicability_score,
                obligation_count=obligation_count,
                assignee_name=assignee_name,
            )

        if self._settings.devrev_send_due_dates and sla_due_date:
            payload[self._settings.devrev_due_date_field] = sla_due_date

        # Person-level assignment wins over the static default owner.
        owner = assignee_user_id or self._settings.devrev_default_owner_id
        if owner:
            payload["owned_by"] = [owner]

        validated = DevRevTicketCreateRequest.model_validate(payload)
        log = logger.bind(external_ref=external_ref, title=title)
        log.info(
            "creating_devrev_ticket",
            group=routing.devrev_group_name,
            body_preview=body[:500],
        )

        response = self._client.post(
            "works.create",
            json_body=validated.model_dump(exclude_none=True),
        )
        work = response.get("work", response)
        log.info(
            "devrev_ticket_created",
            work_id=work.get("id"),
            display_id=work.get("display_id"),
        )
        return response

    def restore_lean_body(
        self,
        *,
        work_id: str,
        analysis: RegulatoryAnalysisOutput,
        source_url: str,
        notification_type: str,
        published_date: str | None,
    ) -> None:
        """Re-apply lean body after DevRev snap-in automation overwrites it."""
        body = build_ticket_body(
            analysis=analysis,
            source_url=source_url,
            notification_type=notification_type,
            published_date=published_date,
        )
        logger.info(
            "devrev_restore_lean_body",
            work_id=work_id,
            body_preview=body[:500],
        )
        self.update_ticket(work_id=work_id, body=body)

    def update_ticket(
        self,
        *,
        work_id: str,
        title: str | None = None,
        body: str | None = None,
        priority: str | None = None,
        tags: list[dict[str, str]] | None = None,
        group_id: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": work_id}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if priority is not None:
            payload["priority"] = priority
        if tags is not None:
            payload["tags"] = tags
        if group_id is not None:
            payload["group"] = group_id
        if severity is not None:
            payload["severity"] = severity

        validated = DevRevTicketUpdateRequest.model_validate(payload)
        return self._client.post(
            "works.update",
            json_body=validated.model_dump(exclude_none=True),
        )

    def find_by_external_ref(self, external_ref: str) -> dict[str, Any] | None:
        try:
            response = self._client.post(
                "works.list",
                json_body={"external_ref": [external_ref], "limit": 1},
            )
        except DevRevAPIError:
            logger.warning("works_list_failed", external_ref=external_ref)
            return None

        works = response.get("works", [])
        return works[0] if works else None

    def create_test_ticket(self) -> dict[str, Any]:
        part_id = self._settings.devrev_default_part_id
        if not part_id:
            raise ValueError("DEVREV_DEFAULT_PART_ID is required for test ticket creation")

        import uuid

        ref = f"sebi-agent-test-{uuid.uuid4().hex[:12]}"
        tag_ids = self._tags.resolve_tag_ids(["sebi-agent-test", "connectivity-test"])
        routing = RoutingDecision(
            primary_team="Compliance Team",
            teams_to_notify=["Compliance Team"],
            devrev_group_name="Compliance Team",
            severity="low",
            escalation_tags=[],
        )
        group_id = self._groups.resolve_group_id(routing.devrev_group_name)
        payload: dict[str, Any] = {
            "type": "ticket",
            "title": "[LOW] SEBI Agent — DevRev Connectivity Test",
            "body": (
                "# Connectivity Test\n\n"
                "This ticket validates DevRev API integration for the SEBI Regulatory "
                "Intelligence Agent v2.\n\n**Safe to close.**"
            ),
            "applies_to_part": part_id,
            "external_ref": ref,
            "tags": tag_ids,
            "severity": "low",
        }
        if group_id:
            payload["group"] = group_id
        validated = DevRevTicketCreateRequest.model_validate(payload)
        return self._client.post("works.create", json_body=validated.model_dump(exclude_none=True))
