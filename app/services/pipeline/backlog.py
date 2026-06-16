"""Re-process notifications that stalled before ticket creation."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.ticket import Ticket
from app.schemas.notification import ScrapedNotification

BACKLOG_INGESTION_STATES = ("extracted", "failed")
BACKLOG_WORKFLOW_STATES = ("analyzed", "pending_human_review")


def notification_to_scraped(notification: Notification) -> ScrapedNotification:
    pdf_urls: list[str] = []
    if notification.pdf_urls:
        try:
            pdf_urls = json.loads(notification.pdf_urls)
        except json.JSONDecodeError:
            pdf_urls = []

    return ScrapedNotification(
        title=notification.title,
        url=notification.url,
        regulator_code=notification.regulator_code or "SEBI",
        published_date=notification.published_date,
        notification_type=notification.notification_type,
        pdf_urls=pdf_urls,
        body_text=notification.body_text or "",
        content_hash=notification.content_hash,
        url_hash=notification.url_hash,
    )


def _ticketed_notification_ids():
    return select(Ticket.notification_id)


def load_backlog_for_ingestion(db: Session, *, limit: int) -> list[Notification]:
    """Notifications scraped but never analyzed / ticketed."""
    return (
        db.query(Notification)
        .filter(Notification.processing_state.in_(BACKLOG_INGESTION_STATES))
        .filter(Notification.id.notin_(_ticketed_notification_ids()))
        .order_by(Notification.created_at.asc())
        .limit(limit)
        .all()
    )


def load_backlog_for_workflow(db: Session, *, limit: int) -> list[Notification]:
    """Notifications analyzed but missing a DevRev ticket row."""
    return (
        db.query(Notification)
        .filter(Notification.processing_state.in_(BACKLOG_WORKFLOW_STATES))
        .filter(Notification.id.notin_(_ticketed_notification_ids()))
        .order_by(Notification.created_at.asc())
        .limit(limit)
        .all()
    )
