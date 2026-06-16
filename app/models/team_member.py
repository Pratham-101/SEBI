"""Roster of assignable people for person-level ticket routing."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TeamMember(Base):
    """A person who can own regulatory tickets in DevRev.

    Seeded from data/roster.json (see AssignmentEngine.sync_roster). Each row
    maps a DevRev dev-user id to a canonical team plus the metadata needed for
    skill/load/seniority-aware assignment.
    """

    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    devrev_user_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    team: Mapped[str] = mapped_column(String(64), index=True)
    # Comma-free JSON list of expertise slugs, e.g. ["mutual-funds", "fpi", "aml"]
    expertise_json: Mapped[str] = mapped_column(Text, default="[]")
    # 1 (junior) .. 5 (head of function)
    seniority: Mapped[int] = mapped_column(Integer, default=3)
    # Soft cap of concurrent open tickets this person should hold
    capacity: Mapped[int] = mapped_column(Integer, default=10)
    # DevRev user id of this person's manager (for CRITICAL escalation notify)
    manager_user_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
