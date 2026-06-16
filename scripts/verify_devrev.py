#!/usr/bin/env python3
"""
Verify DevRev API connectivity and create a test ticket.

Usage (from project root):
  cp .env.example .env   # add DEVREV_API_TOKEN and DEVREV_DEFAULT_PART_ID
  pip install -r requirements.txt
  python scripts/verify_devrev.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.devrev.client import DevRevAPIError, DevRevClient
from app.services.devrev.tickets import DevRevTicketService

configure_logging()
logger = get_logger(__name__)


def main() -> int:
    settings = get_settings()
    if not settings.devrev_api_token:
        print("ERROR: DEVREV_API_TOKEN is not set in .env")
        return 1

    client = DevRevClient()
    print(f"DevRev base URL: {settings.devrev_base_url}")
    print("Step 1: Verifying authentication (dev-users.self)...")

    try:
        self_response = client.verify_connectivity()
        dev_user = self_response.get("dev_user", self_response)
        print("  Auth OK")
        print(f"  User: {dev_user.get('display_name') or dev_user.get('email', 'unknown')}")
        print(f"  ID: {dev_user.get('id', 'n/a')}")
    except DevRevAPIError as exc:
        print(f"  Auth FAILED: {exc}")
        if exc.response_body:
            print(json.dumps(exc.response_body, indent=2))
        return 1

    if not settings.devrev_default_part_id:
        print("\nStep 2: Discovering parts (set DEVREV_DEFAULT_PART_ID in .env)...")
        try:
            parts_resp = client.list_parts(limit=20)
            parts = parts_resp.get("parts", [])
            if not parts:
                print("  No parts returned. Create a Product/Part in DevRev UI first.")
                return 1
            print("  Available parts:")
            for p in parts[:15]:
                print(f"    - {p.get('name')} | id={p.get('id')} | type={p.get('type')}")
            print("\n  Add to .env:")
            print(f"  DEVREV_DEFAULT_PART_ID={parts[0].get('id')}")
            return 1
        except DevRevAPIError as exc:
            print(f"  parts.list FAILED: {exc}")
            return 1

    print("\nStep 2: Creating test ticket...")
    service = DevRevTicketService(client)
    try:
        result = service.create_test_ticket()
        work = result.get("work", result)
        print("  Ticket created successfully")
        print(f"  Work ID: {work.get('id')}")
        print(f"  Display ID: {work.get('display_id')}")
        print(f"  Title: {work.get('title')}")
        logger.info("devrev_test_ticket_created", work_id=work.get("id"))
        print("\nFull API response:")
        print(json.dumps(result, indent=2, default=str)[:4000])
        return 0
    except DevRevAPIError as exc:
        print(f"  Ticket creation FAILED: {exc}")
        if exc.response_body:
            print(json.dumps(exc.response_body, indent=2))
        return 1
    except ValueError as exc:
        print(f"  Configuration error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
