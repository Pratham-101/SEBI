"""DevRev timeline comments for operational intelligence."""

from __future__ import annotations

import structlog

from app.services.devrev.client import DevRevClient

logger = structlog.get_logger(__name__)


class DevRevCommentService:
    def __init__(self, client: DevRevClient | None = None) -> None:
        self._client = client or DevRevClient()

    def add_comment(self, *, work_id: str, body: str) -> dict | None:
        try:
            response = self._client.post(
                "timeline-entries.create",
                json_body={
                    "object": work_id,
                    "type": "timeline_comment",
                    "body": body[:8000],
                },
            )
            logger.info("devrev_comment_added", work_id=work_id)
            return response
        except Exception as exc:
            logger.warning("devrev_comment_failed", work_id=work_id, error=str(exc))
            return None
