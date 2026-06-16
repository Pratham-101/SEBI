"""Machine-readable regulatory obligations."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)
    regulator_code: Mapped[str] = mapped_column(String(16), index=True)
    obligation_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_team: Mapped[str] = mapped_column(String(64), index=True)
    deadline_text: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    devrev_work_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source_basis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
