#!/usr/bin/env python3
"""List DevRev groups with DON ids for .env configuration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.devrev.client import DevRevClient

CANONICAL = [
    ("DEVREV_GROUP_LEGAL", "Legal Team"),
    ("DEVREV_GROUP_COMPLIANCE", "Compliance Team"),
    ("DEVREV_GROUP_FINANCE", "Finance Team"),
    ("DEVREV_GROUP_OPERATIONS", "Operations Team"),
    ("DEVREV_GROUP_INFOSEC", "InfoSec Team"),
    ("DEVREV_GROUP_EXECUTIVE", "Executive Leaders Team"),
]


def main() -> int:
    settings = get_settings()
    if not settings.devrev_api_token:
        print("ERROR: DEVREV_API_TOKEN is not set")
        return 1

    client = DevRevClient()
    response = client.get("groups.list", params={"limit": 100})
    groups = {g.get("name", ""): g.get("id", "") for g in response.get("groups", [])}

    print("# DevRev group IDs (copy into .env)\n")
    for env_key, team_name in CANONICAL:
        gid = groups.get(team_name, "")
        print(f"{env_key}={gid}")

    print("\n# All groups in workspace\n")
    for name in sorted(groups):
        print(f"  {name} -> {groups[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
