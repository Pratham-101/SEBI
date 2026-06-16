"""Intelligence replay — historical regulatory evolution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.intelligence.timeline import IntelligenceTimeline
from app.models.analysis_result import AnalysisResult
from app.models.notification import Notification


class IntelligenceReplay:
    def __init__(self, db: Session) -> None:
        self._db = db

    def replay(
        self,
        *,
        regulator_code: str = "SEBI",
        months: int = 12,
        theme_filter: str | None = None,
    ) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=months * 30)
        q = (
            self._db.query(Notification)
            .filter(Notification.created_at >= since)
            .order_by(Notification.created_at.asc())
        )
        if hasattr(Notification, "regulator_code"):
            q = q.filter(Notification.regulator_code == regulator_code)
        notifications = q.limit(200).all()

        frames = []
        for n in notifications:
            if theme_filter and theme_filter.lower() not in n.title.lower():
                continue
            ar = (
                self._db.query(AnalysisResult)
                .filter(AnalysisResult.notification_id == n.id)
                .order_by(AnalysisResult.id.desc())
                .first()
            )
            events = IntelligenceTimeline(self._db).for_notification(n.id)
            frames.append(
                {
                    "timestamp": n.created_at.isoformat() if n.created_at else None,
                    "notification_id": n.id,
                    "title": n.title,
                    "state": n.processing_state,
                    "priority": ar.priority if ar else None,
                    "events": events,
                }
            )

        return {
            "regulator_code": regulator_code,
            "months": months,
            "theme_filter": theme_filter,
            "frame_count": len(frames),
            "timeline": frames,
            "summary": (
                f"Replay of {regulator_code} regulatory evolution over ~{months} months: "
                f"{len(frames)} notifications with operational event traces."
            ),
        }
