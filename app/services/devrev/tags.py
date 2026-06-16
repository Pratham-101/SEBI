"""Resolve or create DevRev tags by name."""

from __future__ import annotations

import structlog

from app.services.devrev.client import DevRevAPIError, DevRevClient

logger = structlog.get_logger(__name__)

_cache: dict[str, str] = {}


class DevRevTagService:
    def __init__(self, client: DevRevClient | None = None) -> None:
        self._client = client or DevRevClient()

    def get_or_create(self, name: str) -> str:
        normalized = name.strip().lower()
        if normalized in _cache:
            return _cache[normalized]

        existing = self._find_by_name(name)
        if existing:
            tag_id = existing["id"]
            _cache[normalized] = tag_id
            return tag_id

        try:
            response = self._client.post("tags.create", json_body={"name": name})
        except DevRevAPIError as exc:
            if exc.status_code != 409:
                raise
            existing = self._find_by_name(name)
            if not existing:
                raise
            tag_id = existing["id"]
            _cache[normalized] = tag_id
            logger.info("devrev_tag_resolved_after_conflict", name=name, tag_id=tag_id)
            return tag_id

        tag = response.get("tag", response)
        tag_id = tag["id"]
        _cache[normalized] = tag_id
        logger.info("devrev_tag_created", name=name, tag_id=tag_id)
        return tag_id

    def resolve_tag_ids(self, names: list[str]) -> list[dict[str, str]]:
        return [{"id": self.get_or_create(n)} for n in names if n.strip()]

    def _find_by_name(self, name: str) -> dict | None:
        target = name.strip().lower()
        cursor: str | None = None
        for _ in range(10):
            params: dict = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            response = self._client.get("tags.list", params=params)
            for tag in response.get("tags", []):
                if tag.get("name", "").strip().lower() == target:
                    return tag
            cursor = response.get("next_cursor")
            if not cursor:
                break
        return None
