"""Regulatory knowledge relationships — similar notifications and themes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notification import Notification


class RelationshipEngine:
    """Find historically related SEBI notifications for context linking."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def find_related(
        self,
        *,
        themes: list[str],
        notification_type: str,
        exclude_id: int | None = None,
        limit: int = 5,
    ) -> list[dict]:
        if not themes:
            return []

        q = self._db.query(Notification).filter(
            Notification.processing_state.in_(("ticket_created", "analyzed", "pending_human_review"))
        )
        if exclude_id:
            q = q.filter(Notification.id != exclude_id)

        candidates = q.order_by(Notification.created_at.desc()).limit(100).all()
        scored: list[tuple[int, Notification]] = []

        theme_tokens = {t.lower() for t in themes}
        for row in candidates:
            haystack = f"{row.title} {row.notification_type} {row.body_text or ''}".lower()
            score = sum(1 for t in theme_tokens if t in haystack)
            if notification_type and row.notification_type == notification_type:
                score += 1
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": row.id,
                "title": row.title,
                "url": row.url,
                "notification_type": row.notification_type,
                "published_date": row.published_date,
                "relevance_score": score,
            }
            for score, row in scored[:limit]
        ]
