#!/usr/bin/env python3
"""Process specific notifications through RegOps pipeline (create tickets + events)."""

from __future__ import annotations

import argparse
import json
import sys

from app.agents.coordinator import RegOpsCoordinator
from app.core.database import SessionLocal, init_db
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.schemas.notification import ScrapedNotification


def notification_to_scraped(n: Notification) -> ScrapedNotification:
    pdf_urls = []
    if n.pdf_urls:
        try:
            pdf_urls = json.loads(n.pdf_urls)
        except json.JSONDecodeError:
            pass
    return ScrapedNotification(
        title=n.title,
        url=n.url,
        regulator_code=getattr(n, "regulator_code", None) or "SEBI",
        published_date=n.published_date,
        notification_type=n.notification_type or "unknown",
        body_text=n.body_text or "",
        url_hash=n.url_hash,
        content_hash=n.content_hash,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5, help="Max notifications to process")
    parser.add_argument("--ids", type=str, help="Comma-separated notification IDs")
    parser.add_argument("--without-ticket-only", action="store_true", default=True)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    coordinator = RegOpsCoordinator(db)

    if args.ids:
        ids = [int(x.strip()) for x in args.ids.split(",")]
        rows = [db.get(Notification, i) for i in ids]
        rows = [r for r in rows if r]
    else:
        q = db.query(Notification).order_by(Notification.id.desc())
        if args.without_ticket_only:
            ticket_nids = {t.notification_id for t in db.query(Ticket).all()}
            rows = [n for n in q.limit(args.limit * 3).all() if n.id not in ticket_nids][: args.limit]
        else:
            rows = q.limit(args.limit).all()

    if not rows:
        print("No notifications to process.")
        return 0

    print(f"Processing {len(rows)} notification(s)...")
    results = []
    for n in rows:
        print(f"\n--- #{n.id}: {n.title[:70]}... ---")
        item = notification_to_scraped(n)
        try:
            ctx = coordinator.process_single(item)
            results.append(
                {
                    "notification_id": n.id,
                    "title": n.title,
                    "priority": ctx.analysis.priority if ctx.analysis else None,
                    "devrev": ctx.devrev_display_id,
                    "work_id": ctx.devrev_work_id,
                    "obligations": len(ctx.obligations),
                    "war_room": ctx.war_room.get("activated"),
                }
            )
            print(f"  OK → DevRev {ctx.devrev_display_id or 'n/a'} | priority {ctx.analysis.priority if ctx.analysis else 'n/a'}")
        except Exception as exc:
            print(f"  FAILED: {exc}")
            results.append({"notification_id": n.id, "error": str(exc)})

    print("\n=== SUMMARY ===")
    for r in results:
        print(r)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
