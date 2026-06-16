"""Optional Slack/email alerts for escalations."""

from __future__ import annotations

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


def send_slack_alert(message: str) -> bool:
    settings = get_settings()
    if not settings.slack_webhook_url:
        return False
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(settings.slack_webhook_url, json={"text": message})
        return True
    except Exception as exc:
        logger.warning("slack_alert_failed", error=str(exc))
        return False


def notify_escalation(*, title: str, priority: str, url: str) -> None:
    msg = f":warning: *SEBI Regulatory Alert* [{priority}]\n*{title}*\n{url}"
    send_slack_alert(msg)


def notify_scrape_failure(*, regulator_code: str, reason: str, rows_found: int) -> None:
    """Dead-man's-switch alert: the scraper likely failed silently.

    This is the most important alert in the product — if it fires, a regulatory
    notification may have been missed. Logged even when Slack is not configured.
    """
    msg = (
        f":rotating_light: *SCRAPE HEALTH ALERT* — {regulator_code}\n"
        f"Only *{rows_found}* row(s) found. {reason}\n"
        f"Action: verify the {regulator_code} listing page is reachable and the "
        f"layout hasn't changed. Regulatory items may be missed until fixed."
    )
    logger.error(
        "scrape_health_alert",
        regulator_code=regulator_code,
        rows_found=rows_found,
        reason=reason,
    )
    send_slack_alert(msg)
