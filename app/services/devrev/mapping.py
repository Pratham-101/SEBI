"""Map regulatory intelligence fields to DevRev API payloads."""

from __future__ import annotations

from app.schemas.analysis import PriorityLevel, RegulatoryAnalysisOutput
from app.services.routing.team_router import RoutingDecision, normalize_team, team_to_tag_slug


PRIORITY_TO_DEVREV: dict[str, str] = {
    PriorityLevel.CRITICAL.value: "p0",
    PriorityLevel.HIGH.value: "p1",
    PriorityLevel.MEDIUM.value: "p2",
    PriorityLevel.LOW.value: "p3",
}


def format_ticket_title(
    analysis: RegulatoryAnalysisOutput,
    *,
    notification_date: str | None = None,
) -> str:
    priority = analysis.priority.upper()
    base = analysis.ticket_title.strip() or "SEBI Regulatory Update"
    if base.startswith("["):
        title = base
    else:
        title = f"[{priority}] {base}"
    if notification_date and notification_date not in title:
        date_short = notification_date.split(",")[0].strip()[:24]
        if len(title) + len(date_short) < 240:
            title = f"{title} - {date_short}"
    return title[:256]


def build_ticket_body(
    *,
    analysis: RegulatoryAnalysisOutput,
    source_url: str,
    notification_type: str,
    published_date: str | None,
    severity: str | None = None,
    metadata: dict | None = None,
    related_notifications: list[dict] | None = None,
    assignee_name: str | None = None,
    compliance_deadline: str | None = None,
    sla_due_date: str | None = None,
) -> str:
    """Lean parent ticket body: key metadata, summary, source link."""
    del notification_type, metadata, related_notifications

    notif_date = published_date or "Unknown"
    severity_label = (severity or analysis.priority or "medium").upper()

    meta_lines = [
        f"Severity: {severity_label}",
        f"Published: {notif_date}",
    ]
    if assignee_name:
        meta_lines.append(f"Owner: {assignee_name}")
    if compliance_deadline:
        meta_lines.append(f"Compliance deadline: {compliance_deadline}")
    if sla_due_date:
        meta_lines.append(f"Internal SLA due: {sla_due_date}")

    source_section = ""
    if source_url and source_url.strip():
        source_section = (
            f"\n---\n"
            f"Source: [SEBI Original Notification]({source_url.strip()})\n"
        )

    return (
        "\n".join(meta_lines) + "\n\n"
        f"{analysis.executive_summary.strip()}\n"
        f"{source_section}"
    )


def build_insight_child_body(
    *,
    insight,
    parent_display_id: str,
    published_date: str | None = None,
    assignee_name: str | None = None,
    due_date: str | None = None,
) -> str:
    """Markdown body for a child work item from one actionable insight."""
    deps = insight.dependencies.strip() if insight.dependencies else "None identified"

    meta_lines = [
        f"**Parent ticket:** {parent_display_id}",
        f"**Owner team:** {insight.owner_team}",
    ]
    if assignee_name:
        meta_lines.append(f"**Assigned to:** {assignee_name}")
    meta_lines.append(f"**Urgency:** {insight.urgency.upper()}")
    if due_date:
        meta_lines.append(f"**Target due date:** {due_date}")
    if published_date:
        meta_lines.append(f"**Regulatory publication date:** {published_date}")
    meta_lines.append(f"**Dependencies:** {deps}")

    return (
        "\n\n".join(meta_lines) + "\n\n"
        f"## Action\n\n{insight.action.strip()}\n\n"
        f"## Definition of done\n\n"
        f"- [ ] {insight.action.strip()}\n"
        f"- [ ] Evidence/artifact attached or linked\n"
        f"- [ ] {insight.owner_team} sign-off recorded\n"
    )


def map_priority(priority: str) -> str:
    normalized = priority.strip().upper()
    return PRIORITY_TO_DEVREV.get(normalized, "p2")


def _slug(value: str, *, max_len: int = 48) -> str:
    cleaned = "-".join(value.strip().lower().split())
    cleaned = "".join(c for c in cleaned if c.isalnum() or c in "-:.")
    return cleaned[:max_len].strip("-")


def collect_namespaced_tags(
    analysis: RegulatoryAnalysisOutput,
    *,
    routing: RoutingDecision | None = None,
    regulator_code: str = "SEBI",
    notification_type: str = "",
    applicability_score: float | None = None,
    effective_date: str | None = None,
    obligation_count: int | None = None,
) -> list[str]:
    """Consistent, filterable tag taxonomy using `key:value` namespaces.

    Examples: reg:sebi, domain:mutual-funds, type:circular, pri:p1,
    team:compliance, impact:firmwide, applies:yes, deadline:2026-07-01.
    """
    names: list[str] = [
        f"reg:{_slug(regulator_code)}",
        f"pri:{map_priority(analysis.priority)}",
        f"sev:{_slug(analysis.priority)}",
    ]

    # Tenant tag for traceability when several banks share tooling/dashboards.
    from app.core.config import get_settings

    _tid = get_settings().tenant_id
    if _tid and _tid != "default":
        names.append(f"tenant:{_slug(_tid)}")

    domain = _slug(analysis.regulatory_domain or "")
    if domain:
        names.append(f"domain:{domain}")
    if notification_type:
        names.append(f"type:{_slug(notification_type)}")

    # Free-form analyst tags kept, but namespaced as topic:
    for tag in analysis.tags:
        if tag.startswith("don:"):
            continue
        names.append(f"topic:{_slug(tag)}")

    if routing:
        names.append(f"team:{team_to_tag_slug(routing.primary_team)}")
        for team in routing.teams_to_notify:
            slug = team_to_tag_slug(normalize_team(team))
            names.append(f"notify:{slug}")

    if analysis.requires_executive_escalation:
        names.append("impact:firmwide")
    if analysis.requires_immediate_attention:
        names.append("flag:urgent")

    if applicability_score is not None:
        names.append("applies:yes" if applicability_score >= 0.35 else "applies:low")

    if effective_date:
        names.append(f"deadline:{_slug(effective_date, max_len=16)}")

    if obligation_count is not None and obligation_count > 0:
        names.append(f"obligations:{min(obligation_count, 99)}")

    # Dedupe, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.lower()
        if n and key not in seen:
            seen.add(key)
            out.append(n)
    return out


def build_custom_fields(
    analysis: RegulatoryAnalysisOutput,
    *,
    regulator_code: str = "SEBI",
    effective_date: str | None = None,
    compliance_deadline: str | None = None,
    sla_due_date: str | None = None,
    applicability_score: float | None = None,
    obligation_count: int | None = None,
    assignee_name: str | None = None,
) -> dict:
    """DevRev custom_fields payload (tenant must define matching ctype fields).

    Keys use the conventional `tnt__` custom-field prefix; adjust to match the
    field ids configured in your DevRev workspace.
    """
    fields: dict = {
        "tnt__regulator": regulator_code,
        "tnt__regulatory_domain": analysis.regulatory_domain,
        "tnt__priority": analysis.priority,
        "tnt__confidence": round(analysis.confidence_score, 2),
    }
    if effective_date:
        fields["tnt__effective_date"] = effective_date
    if compliance_deadline:
        fields["tnt__compliance_deadline"] = compliance_deadline
    if sla_due_date:
        fields["tnt__sla_due_date"] = sla_due_date
    if applicability_score is not None:
        fields["tnt__applicability_score"] = round(applicability_score, 3)
    if obligation_count is not None:
        fields["tnt__obligation_count"] = obligation_count
    if assignee_name:
        fields["tnt__assignee"] = assignee_name
    return fields


def collect_tag_names(
    analysis: RegulatoryAnalysisOutput,
    *,
    routing: RoutingDecision | None = None,
) -> list[str]:
    """Tag names for DevRev tags API, including team:xxx for notify teams."""
    names: list[str] = []
    for tag in analysis.tags:
        if tag.startswith("don:"):
            continue
        names.append(tag.replace(" ", "-")[:48])

    names.extend(
        [
            "sebi-regulatory",
            f"priority-{analysis.priority.lower()}",
            "compliance-update",
        ]
    )

    domain = analysis.regulatory_domain.replace(" ", "-").lower()
    if domain:
        names.append(domain[:40])

    if analysis.requires_immediate_attention:
        names.append("urgent-review")
    if analysis.requires_executive_escalation:
        names.append("executive-attention")

    if routing:
        primary_slug = team_to_tag_slug(routing.primary_team)
        for team in routing.teams_to_notify:
            normalized = normalize_team(team)
            slug = team_to_tag_slug(normalized)
            if slug != primary_slug:
                names.append(f"team:{slug}")

    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out


def collect_insight_tag_names(
    analysis: RegulatoryAnalysisOutput,
    *,
    parent_tag_names: list[str],
    owner_team: str,
) -> list[str]:
    """Tags for child insight tickets: inherit parent tags plus owner team tag."""
    owner_slug = team_to_tag_slug(owner_team)
    combined = list(parent_tag_names) + [f"team:{owner_slug}", "actionable-insight"]
    seen: set[str] = set()
    out: list[str] = []
    for n in combined:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out
