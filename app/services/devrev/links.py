"""DevRev work item link operations (parent-child)."""

from __future__ import annotations

import time

import structlog

from app.services.devrev.client import DevRevAPIError, DevRevClient

logger = structlog.get_logger(__name__)

PRIMARY_LINK_TYPE = "is_dependent_on"
LINK_ATTEMPT_DELAY_SECONDS = 0.5
MAX_LINK_RETRIES = 3


class DevRevLinkService:
    def __init__(self, client: DevRevClient | None = None) -> None:
        self._client = client or DevRevClient()

    def link_parent_child(self, *, parent_work_id: str, child_work_id: str) -> bool:
        """Link parent ticket to child issue. Returns True when linked."""
        attempts = [
            (PRIMARY_LINK_TYPE, parent_work_id, child_work_id),
            (PRIMARY_LINK_TYPE, child_work_id, parent_work_id),
        ]
        for link_type, source, target in attempts:
            if self._create_link_with_retry(
                link_type=link_type,
                source=source,
                target=target,
                parent_work_id=parent_work_id,
                child_work_id=child_work_id,
            ):
                return True
            time.sleep(LINK_ATTEMPT_DELAY_SECONDS)
        return False

    def _create_link_with_retry(
        self,
        *,
        link_type: str,
        source: str,
        target: str,
        parent_work_id: str,
        child_work_id: str,
    ) -> bool:
        for attempt in range(1, MAX_LINK_RETRIES + 1):
            logger.info(
                "link_attempt",
                parent=parent_work_id,
                child=child_work_id,
                link_type=link_type,
                source=source,
                target=target,
                attempt=attempt,
            )
            try:
                self._client.post(
                    "links.create",
                    json_body={
                        "link_type": link_type,
                        "source": source,
                        "target": target,
                    },
                )
                logger.info(
                    "link_success",
                    parent=parent_work_id,
                    child=child_work_id,
                    link_type=link_type,
                    status="created",
                    attempt=attempt,
                )
                return True
            except DevRevAPIError as exc:
                if exc.status_code == 409:
                    logger.info(
                        "link_success",
                        parent=parent_work_id,
                        child=child_work_id,
                        link_type=link_type,
                        status="already_exists",
                        attempt=attempt,
                    )
                    return True
                logger.error(
                    "link_failed",
                    parent=parent_work_id,
                    child=child_work_id,
                    link_type=link_type,
                    status=exc.status_code,
                    response_body=exc.response_body,
                    attempt=attempt,
                )
                if attempt < MAX_LINK_RETRIES:
                    time.sleep(LINK_ATTEMPT_DELAY_SECONDS * attempt)
            except Exception as exc:
                logger.error(
                    "link_failed",
                    parent=parent_work_id,
                    child=child_work_id,
                    link_type=link_type,
                    status="error",
                    error=str(exc),
                    attempt=attempt,
                )
                if attempt < MAX_LINK_RETRIES:
                    time.sleep(LINK_ATTEMPT_DELAY_SECONDS * attempt)
        return False
