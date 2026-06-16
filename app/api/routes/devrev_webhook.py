"""DevRev webhook endpoint for /ask copilot commands."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.devrev.webhook_handler import DevRevWebhookHandler

router = APIRouter(prefix="/devrev", tags=["devrev"])


@router.post("/webhook")
async def devrev_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw = await request.body()
    signature = request.headers.get("X-DevRev-Signature") or request.headers.get(
        "x-devrev-signature"
    )

    handler = DevRevWebhookHandler(db)
    if not handler.verify_signature(raw, signature):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json") from exc

    return handler.handle_event(payload)
