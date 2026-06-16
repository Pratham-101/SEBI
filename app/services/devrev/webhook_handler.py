"""Handle DevRev webhook events for RegOps Copilot /ask commands."""

from __future__ import annotations

import hashlib
import hmac
import re

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.copilot.service import RegOpsCopilot
from app.services.devrev.comments import DevRevCommentService

logger = structlog.get_logger(__name__)

ASK_PREFIX = re.compile(r"^\s*/ask\s+(.+)", re.IGNORECASE | re.DOTALL)
BOT_MARKER = "regops-copilot-reply"


class DevRevWebhookHandler:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._comments = DevRevCommentService()
        self._settings = get_settings()

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        secret = (self._settings.devrev_webhook_secret or "").strip()
        if not secret:
            logger.warning("devrev_webhook_no_secret", msg="skipping signature verification")
            return True
        if not signature_header:
            return False
        expected = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        provided = signature_header.removeprefix("sha256=").strip()
        return hmac.compare_digest(expected, provided)

    def handle_event(self, payload: dict) -> dict:
        event_type = payload.get("type") or _detect_event_type(payload)
        logger.info("devrev_webhook_received", event_type=event_type)

        if event_type == "timeline_entry_created":
            return self._handle_timeline_entry(payload)

        return {"handled": False, "reason": f"ignored_event:{event_type}"}

    def _handle_timeline_entry(self, payload: dict) -> dict:
        entry_wrap = payload.get("timeline_entry_created") or payload
        entry = entry_wrap.get("entry") or entry_wrap.get("timeline_entry") or entry_wrap
        if not entry:
            return {"handled": False, "reason": "missing_entry"}

        if entry.get("type") != "timeline_comment":
            return {"handled": False, "reason": "not_a_comment"}

        body = (entry.get("body") or "").strip()
        if BOT_MARKER in body:
            return {"handled": False, "reason": "bot_comment_ignored"}

        match = ASK_PREFIX.match(body)
        if not match:
            return {"handled": False, "reason": "not_ask_command"}

        question = match.group(1).strip()
        work_id = _extract_work_id(entry)
        if not work_id:
            return {"handled": False, "reason": "missing_work_id"}

        result = RegOpsCopilot(self._db).answer(question)
        reply = _format_copilot_reply(result)
        self._comments.add_comment(work_id=work_id, body=reply)
        logger.info("devrev_ask_replied", work_id=work_id, question=question[:120])
        return {"handled": True, "work_id": work_id, "question": question}


def _detect_event_type(payload: dict) -> str:
    for key in payload:
        if key.endswith("_created") or key.endswith("_updated") or key.endswith("_deleted"):
            return key
    return "unknown"


def _extract_work_id(entry: dict) -> str | None:
    obj = entry.get("object") or entry.get("work") or {}
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("id")
    return entry.get("object_id") or entry.get("id")


def _format_copilot_reply(result: dict) -> str:
    lines = [
        f"**RegOps Copilot** ({BOT_MARKER})",
        "",
        result.get("answer", "No answer generated."),
    ]

    tickets = result.get("ticket_references") or []
    if tickets:
        lines.append("")
        lines.append("**DevRev tickets**")
        for t in tickets:
            url = t.get("url") or ""
            label = t.get("display_id") or "ticket"
            title = t.get("title") or ""
            if url:
                lines.append(f"- [{label}]({url}): {title}")
            else:
                lines.append(f"- {label}: {title}")

    sebi = result.get("sebi_sources") or []
    if sebi:
        lines.append("")
        lines.append("**SEBI sources**")
        for s in sebi:
            lines.append(f"- [{s.get('title', 'SEBI')}]({s.get('url', '')})")

    web = result.get("web_sources") or []
    if web:
        lines.append("")
        lines.append("**Web sources**")
        for s in web:
            lines.append(f"- [{s.get('title', 'source')}]({s.get('url', '')})")

    if result.get("used_web_search"):
        lines.append("")
        lines.append("_Answer includes web search results._")

    return "\n".join(lines)[:7900]
