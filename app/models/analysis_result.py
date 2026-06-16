"""AI analysis result ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured_output: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(16))
    governance_status: Mapped[str] = mapped_column(String(32), default="pending")
    requires_human_review: Mapped[bool] = mapped_column(default=False)
    teams_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadlines_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_items_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    escalation_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    routing_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    notification = relationship("Notification", back_populates="analysis_results")
