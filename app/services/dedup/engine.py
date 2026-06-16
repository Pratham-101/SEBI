"""Deduplication using URL and content hashes."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.schemas.notification import ScrapedNotification


def hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def hash_content(content: str) -> str:
    normalized = " ".join((content or "").split()).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


# SHA-256 of empty string — must not be used for cross-item dedup on listing-only rows
EMPTY_CONTENT_HASH = hash_content("")


class DeduplicationEngine:
    def __init__(self, db: Session) -> None:
        self._db = db

    def is_duplicate(self, item: ScrapedNotification) -> Notification | None:
        url_h = item.url_hash or hash_url(item.url)
        existing = (
            self._db.query(Notification)
            .filter(Notification.url_hash == url_h)
            .first()
        )
        if existing:
            return existing

        # Only dedupe by content when we have real body text (post-enrichment).
        content_h = item.content_hash or ""
        if (
            content_h
            and content_h != EMPTY_CONTENT_HASH
            and not content_h.startswith("pending:")
        ):
            return (
                self._db.query(Notification)
                .filter(Notification.content_hash == content_h)
                .first()
            )
        return None

    def enrich_hashes(self, item: ScrapedNotification) -> ScrapedNotification:
        item.url_hash = hash_url(item.url)
        if (item.body_text or "").strip():
            item.content_hash = hash_content(item.body_text)
        else:
            # Unique per URL until detail page is fetched — avoids false "duplicate of #33"
            item.content_hash = f"pending:{item.url_hash}"
        return item
