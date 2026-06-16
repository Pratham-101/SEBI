"""Compliance Console API — clean, customer-facing monitoring + drill-down.

Purpose-built for the light dashboard. Returns plain, business-readable data
(latest SEBI updates, priority, owning team/person, deadline, DevRev ticket link)
with filtering and a detail view. Deliberately avoids the internal
"pressure/heatmap/war-room" intelligence surfaces.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.analysis_result import AnalysisResult
from app.models.notification import Notification
from app.models.obligation import Obligation
from app.models.ticket import Ticket

router = APIRouter(prefix="/console", tags=["console"])

_PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _ticket_url(display_id: str | None) -> str | None:
    if not display_id:
        return None
    base = get_settings().devrev_workspace_url.strip().rstrip("/")
    if not base:
        return None
    return f"{base}/works/{display_id}"


def _load_analysis(row: AnalysisResult | None) -> dict:
    if not row or not row.structured_output:
        return {}
    try:
        return json.loads(row.structured_output)
    except json.JSONDecodeError:
        return {}


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    """Headline counters for the top of the console."""
    settings = get_settings()
    total = db.query(Notification).count()
    tickets = db.query(Ticket).count()
    high = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.priority.in_(("HIGH", "CRITICAL")))
        .count()
    )
    open_obligations = (
        db.query(Obligation)
        .filter(Obligation.status.notin_(("completed", "validated", "closed")))
        .count()
    )
    return {
        "tenant": settings.tenant_name,
        "regulator": settings.active_regulator,
        "total_updates": total,
        "tickets_created": tickets,
        "high_priority": high,
        "open_obligations": open_obligations,
        "scan_interval_minutes": settings.cron_interval_minutes,
    }


@router.get("/updates")
def updates(
    db: Session = Depends(get_db),
    priority: str | None = Query(default=None, description="LOW|MEDIUM|HIGH|CRITICAL"),
    team: str | None = Query(default=None, description="filter by owning team"),
    status: str | None = Query(default=None, description="ticketed|pending"),
    search: str | None = Query(default=None, description="title contains"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Filterable list of SEBI updates with their priority, owner and ticket."""
    q = db.query(Notification).order_by(Notification.created_at.desc())
    if search:
        q = q.filter(Notification.title.ilike(f"%{search.strip()}%"))
    notifications = q.limit(500).all()  # cap then filter in Python on joined data

    rows = []
    for n in notifications:
        analysis_row = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.notification_id == n.id)
            .order_by(AnalysisResult.id.desc())
            .first()
        )
        ticket = (
            db.query(Ticket)
            .filter(Ticket.notification_id == n.id)
            .order_by(Ticket.id.desc())
            .first()
        )
        data = _load_analysis(analysis_row)
        item_priority = (analysis_row.priority if analysis_row else None) or "—"
        team_name = ticket.assigned_team if ticket else (data.get("suggested_owner_team"))
        assignee = ticket.assignee_name if ticket else None
        item_status = "ticketed" if ticket else "pending"

        if priority and item_priority.upper() != priority.upper():
            continue
        if team and (team_name or "").lower() != team.lower():
            continue
        if status and item_status != status.lower():
            continue

        rows.append(
            {
                "id": n.id,
                "title": n.title,
                "type": n.notification_type,
                "published_date": n.published_date,
                "priority": item_priority,
                "team": team_name or "—",
                "assignee": assignee,
                "status": item_status,
                "devrev_display_id": ticket.devrev_display_id if ticket else None,
                "devrev_url": _ticket_url(ticket.devrev_display_id if ticket else None),
                "source_url": n.url,
                "summary": (data.get("executive_summary") or "")[:240],
            }
        )

    # Sort by priority then recency (most severe, newest first).
    rows.sort(key=lambda r: (_PRIORITY_RANK.get(str(r["priority"]).upper(), 9)))
    total = len(rows)
    return {"total": total, "items": rows[offset : offset + limit]}


@router.get("/updates/{notification_id}")
def update_detail(notification_id: int, db: Session = Depends(get_db)) -> dict:
    """Full drill-down for one SEBI update."""
    n = db.get(Notification, notification_id)
    if not n:
        return {"error": "not_found"}
    analysis_row = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.notification_id == n.id)
        .order_by(AnalysisResult.id.desc())
        .first()
    )
    ticket = (
        db.query(Ticket)
        .filter(Ticket.notification_id == n.id)
        .order_by(Ticket.id.desc())
        .first()
    )
    data = _load_analysis(analysis_row)
    obligations = (
        db.query(Obligation).filter(Obligation.notification_id == n.id).all()
    )

    return {
        "id": n.id,
        "title": n.title,
        "type": n.notification_type,
        "published_date": n.published_date,
        "regulator": getattr(n, "regulator_code", "SEBI"),
        "source_url": n.url,
        "priority": (analysis_row.priority if analysis_row else None),
        "confidence": (analysis_row.confidence_score if analysis_row else None),
        "summary": data.get("executive_summary"),
        "regulatory_domain": data.get("regulatory_domain"),
        "compliance_risk": data.get("compliance_risk"),
        "operational_risk": data.get("operational_risk"),
        "key_changes": data.get("key_regulatory_changes", []),
        "action_items": [
            {
                "action": i.get("action"),
                "owner_team": i.get("owner_team"),
                "urgency": i.get("urgency"),
            }
            for i in data.get("actionable_insights", [])
        ],
        "important_dates": data.get("important_dates", []),
        "team": ticket.assigned_team if ticket else data.get("suggested_owner_team"),
        "assignee": ticket.assignee_name if ticket else None,
        "devrev_display_id": ticket.devrev_display_id if ticket else None,
        "devrev_url": _ticket_url(ticket.devrev_display_id if ticket else None),
        "obligations": [
            {
                "description": o.description,
                "type": o.obligation_type,
                "owner_team": o.owner_team,
                "deadline": o.deadline_text,
                "status": o.status,
                "risk_level": o.risk_level,
            }
            for o in obligations
        ],
    }
