"""DevRev ticket tracking ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)
    devrev_work_id: Mapped[str] = mapped_column(String(256), index=True)
    devrev_display_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    external_ref: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    priority: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="created")
    ticket_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    devrev_group_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    assigned_team: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    assignee_user_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    assignee_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    assignment_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subtask_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    notification = relationship("Notification", back_populates="tickets")
