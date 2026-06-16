from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.ticket import Ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketResponse(BaseModel):
    id: int
    notification_id: int
    devrev_work_id: str
    devrev_display_id: str | None
    external_ref: str
    priority: str
    status: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[TicketResponse])
def list_tickets(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Ticket]:
    return (
        db.query(Ticket)
        .order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
