"""WebSocket real-time intelligence stream."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.bus import EventBus
from app.intelligence.narrator import OperationalNarrator
from app.core.database import SessionLocal

router = APIRouter(tags=["stream"])


@router.websocket("/ws/intelligence")
async def intelligence_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = EventBus.get()
    queue = await bus.subscribe()

    db = SessionLocal()
    try:
        brief = OperationalNarrator(db).generate_brief()
        await websocket.send_json({"event_type": "narrator", **brief})
    finally:
        db.close()

    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                await websocket.send_text(payload)
            except asyncio.TimeoutError:
                await websocket.send_json(
                    {"event_type": "heartbeat", "timestamp": asyncio.get_event_loop().time()}
                )
    except WebSocketDisconnect:
        pass
    finally:
        await bus.unsubscribe(queue)
