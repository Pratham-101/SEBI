"""Schemas for scraped SEBI notifications."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class ScrapedNotification(BaseModel):
    title: str
    url: str
    regulator_code: str = "SEBI"
    published_date: str | None = None
    notification_type: str = "unknown"
    pdf_urls: list[str] = Field(default_factory=list)
    body_text: str = ""
    content_hash: str = ""
    url_hash: str = ""


class NotificationResponse(BaseModel):
    id: int
    title: str
    url: str
    regulator_code: str = "SEBI"
    notification_type: str
    published_date: str | None
    processing_state: str
    url_hash: str
    content_hash: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
