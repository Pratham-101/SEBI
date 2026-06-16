"""Per-run scraper health record — powers the dead-man's-switch alert."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScrapeHealth(Base):
    """One row per scrape attempt. Lets us detect silent failures (0 rows) and
    sudden drops vs the recent baseline — the worst failure mode for a
    "we watch SEBI for you" product."""

    __tablename__ = "scrape_health"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    regulator_code: Mapped[str] = mapped_column(String(16), default="SEBI", index=True)
    rows_found: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
