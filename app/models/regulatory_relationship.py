"""Knowledge graph edges between regulatory entities."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RegulatoryRelationship(Base):
    __tablename__ = "regulatory_relationships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_entity_id: Mapped[int] = mapped_column(index=True)
    target_entity_id: Mapped[int] = mapped_column(index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), index=True)
    strength: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
