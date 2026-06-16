"""SLA tracking for regulatory obligations and tickets."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SlaTracking(Base):
    __tablename__ = "sla_tracking"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    obligation_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    notification_id: Mapped[int] = mapped_column(index=True)
    devrev_work_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    target_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    breached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="on_track", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
