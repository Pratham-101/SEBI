"""Human-AI collaboration decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HumanDecision(Base):
    __tablename__ = "human_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    obligation_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    proposal_type: Mapped[str] = mapped_column(String(64))
    proposal_json: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    modifier_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(128), default="operator")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
