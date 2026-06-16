"""Scrape health recording + dead-man's-switch alerting.

Called by the coordinator right after a scrape. Persists a ScrapeHealth row and
fires an alert when the result looks like a silent failure:
  - fewer than scrape_min_expected_rows (0 usually = layout change / block), or
  - a sharp drop below the recent rolling average of successful scrapes.
"""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.scrape_health import ScrapeHealth
from app.services.notifications.alerts import notify_scrape_failure

logger = structlog.get_logger(__name__)


def record_scrape_health(
    db: Session,
    *,
    regulator_code: str,
    rows_found: int,
    attempts: int = 1,
    duration_ms: int | None = None,
) -> ScrapeHealth:
    settings = get_settings()
    reason = None
    ok = True
    alerted = False

    # Rolling baseline from recent healthy scrapes (exclude the current one).
    recent = (
        db.query(ScrapeHealth.rows_found)
        .filter(
            ScrapeHealth.regulator_code == regulator_code,
            ScrapeHealth.ok.is_(True),
        )
        .order_by(ScrapeHealth.id.desc())
        .limit(20)
        .all()
    )
    counts = [r[0] for r in recent if r[0] is not None]
    baseline = (sum(counts) / len(counts)) if counts else None

    if rows_found < settings.scrape_min_expected_rows:
        ok = False
        reason = (
            f"Below minimum expected ({settings.scrape_min_expected_rows}). "
            "Likely a layout change, network failure, or block."
        )
    elif baseline and rows_found < baseline * settings.scrape_drop_alert_ratio:
        ok = False
        reason = (
            f"Sharp drop: {rows_found} vs recent avg {baseline:.1f}. "
            "Listing may be partially broken."
        )

    if not ok:
        try:
            notify_scrape_failure(
                regulator_code=regulator_code,
                reason=reason or "Scrape health degraded.",
                rows_found=rows_found,
            )
            alerted = True
        except Exception as exc:  # noqa: BLE001 — never let alerting break the run
            logger.warning("scrape_alert_failed", error=str(exc))

    row = ScrapeHealth(
        regulator_code=regulator_code,
        rows_found=rows_found,
        attempts=attempts,
        ok=ok,
        alerted=alerted,
        reason=reason,
        duration_ms=duration_ms,
    )
    db.add(row)
    db.commit()
    logger.info(
        "scrape_health_recorded",
        regulator_code=regulator_code,
        rows_found=rows_found,
        ok=ok,
        baseline=round(baseline, 1) if baseline else None,
    )
    return row
