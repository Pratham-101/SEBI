#!/usr/bin/env python3
"""List DevRev dev-users with DON ids for data/roster.json configuration.

Copy each user's `id` into the `devrev_user_id` field of the matching roster
member in data/roster.json, then run scripts/sync_roster.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.devrev.client import DevRevClient


def main() -> int:
    settings = get_settings()
    if not settings.devrev_api_token:
        print("ERROR: DEVREV_API_TOKEN is not set")
        return 1

    client = DevRevClient()
    response = client.get("dev-users.list", params={"limit": 100})
    users = response.get("dev_users", []) or response.get("users", [])

    print("# DevRev dev-users (copy `id` into data/roster.json)\n")
    for u in users:
        name = u.get("display_name") or u.get("full_name") or "(no name)"
        email = u.get("email", "")
        print(f"  {name:32} {email:32} -> {u.get('id', '')}")
    print(f"\n{len(users)} users found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
