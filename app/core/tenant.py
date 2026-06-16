"""Multi-tenant configuration.

Model: ONE deployment per bank, selected by the `TENANT` env var. A tenant file
(data/tenants/<id>.json) overrides the relevant settings fields at startup — DevRev
credentials, part/groups/owner, the org profile, the roster, and the listing URL.

Because each bank runs as its own process + its own database, there is no shared
state and therefore no cross-tenant data-leak risk — the right trade-off for a
low-cost pilot. Running several tenants inside one process can be layered on later
without changing the tenant file format.

If `TENANT` is unset, behaviour is identical to the original single-tenant app
(everything comes from .env).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Tenant file keys -> Settings attribute names. Only these are overridable.
_FIELD_MAP: dict[str, str] = {
    "devrev_api_token": "devrev_api_token",
    "devrev_base_url": "devrev_base_url",
    "devrev_default_part_id": "devrev_default_part_id",
    "devrev_default_owner_id": "devrev_default_owner_id",
    "devrev_workspace_url": "devrev_workspace_url",
    "devrev_webhook_secret": "devrev_webhook_secret",
    "devrev_group_legal": "devrev_group_legal",
    "devrev_group_compliance": "devrev_group_compliance",
    "devrev_group_finance": "devrev_group_finance",
    "devrev_group_operations": "devrev_group_operations",
    "devrev_group_infosec": "devrev_group_infosec",
    "devrev_group_executive": "devrev_group_executive",
    "applicability_profile_path": "applicability_profile_path",
    "assignment_roster_path": "assignment_roster_path",
    "sebi_listing_url": "sebi_listing_url",
    "active_regulator": "active_regulator",
    "slack_webhook_url": "slack_webhook_url",
}

_TENANTS_DIR = Path("data/tenants")


def active_tenant_id() -> str | None:
    tid = os.environ.get("TENANT", "").strip()
    return tid or None


def _tenant_file(tenant_id: str) -> Path:
    return _TENANTS_DIR / f"{tenant_id}.json"


def load_tenant(tenant_id: str) -> dict:
    path = _tenant_file(tenant_id)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise FileNotFoundError(
            f"TENANT='{tenant_id}' but {path} not found. "
            f"Create it (see data/tenants/example.json)."
        )
    return json.loads(path.read_text())


def apply_tenant_overrides(settings) -> None:
    """Mutate a Settings instance in place with the active tenant's values.

    Called once from get_settings() after construction. No-op when TENANT unset.
    """
    tenant_id = active_tenant_id()
    if not tenant_id:
        return
    try:
        data = load_tenant(tenant_id)
    except FileNotFoundError as exc:
        logger.error("tenant_config_missing", error=str(exc))
        raise

    applied: list[str] = []
    for key, attr in _FIELD_MAP.items():
        if key in data and data[key] not in (None, ""):
            setattr(settings, attr, data[key])
            applied.append(attr)

    # Stash identity for tagging/logging.
    settings.tenant_id = tenant_id
    settings.tenant_name = data.get("name", tenant_id)
    logger.info(
        "tenant_overrides_applied",
        tenant_id=tenant_id,
        name=settings.tenant_name,
        fields=len(applied),
    )
