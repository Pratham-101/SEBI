"""Notification ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False, index=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    regulator_code: Mapped[str] = mapped_column(String(16), default="SEBI", index=True)
    notification_type: Mapped[str] = mapped_column(String(64), default="unknown")
    published_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_state: Mapped[str] = mapped_column(String(32), default="discovered", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    analysis_results = relationship("AnalysisResult", back_populates="notification")
    tickets = relationship("Ticket", back_populates="notification")
    processing_logs = relationship("ProcessingLog", back_populates="notification")
