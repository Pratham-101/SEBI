"""DevRev group resolution via configured group IDs."""

from __future__ import annotations

import structlog

from app.core.config import get_settings
from app.services.devrev.client import DevRevClient
from app.services.routing.team_router import (
    TEAM_COMPLIANCE,
    TEAM_EXECUTIVE,
    TEAM_FINANCE,
    TEAM_INFOSEC,
    TEAM_LEGAL,
    TEAM_OPERATIONS,
    normalize_team,
)

logger = structlog.get_logger(__name__)

_group_cache: dict[str, str] = {}


class DevRevGroupService:
    """Resolve DevRev group IDs by canonical team name."""

    def __init__(self, client: DevRevClient | None = None) -> None:
        self._client = client or DevRevClient()
        self._settings = get_settings()

    def _configured_group_ids(self) -> dict[str, str]:
        return {
            TEAM_LEGAL: self._settings.devrev_group_legal,
            TEAM_COMPLIANCE: self._settings.devrev_group_compliance,
            TEAM_FINANCE: self._settings.devrev_group_finance,
            TEAM_OPERATIONS: self._settings.devrev_group_operations,
            TEAM_INFOSEC: self._settings.devrev_group_infosec,
            TEAM_EXECUTIVE: self._settings.devrev_group_executive,
        }

    def resolve_group_id(self, name: str) -> str | None:
        canonical = normalize_team(name)
        normalized = canonical.strip().lower()
        if normalized in _group_cache:
            return _group_cache[normalized]

        configured = self._configured_group_ids().get(canonical, "").strip()
        if configured:
            _group_cache[normalized] = configured
            return configured

        response = self._client.get("groups.list", params={"limit": 100})
        for group in response.get("groups", []):
            gname = (group.get("name") or "").strip().lower()
            _group_cache[gname] = group["id"]
            if gname == normalized or canonical.lower() in gname:
                return group["id"]

        logger.warning("devrev_group_not_found", team=canonical)
        return None

    def resolve_group_id_for_team(self, team: str) -> str | None:
        return self.resolve_group_id(normalize_team(team))
