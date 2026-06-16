from fastapi import APIRouter

from app.api.routes import audit, command_center, console, devrev_webhook, health, notifications, regops, stream, tickets, trigger

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(notifications.router)
api_router.include_router(tickets.router)
api_router.include_router(audit.router)
api_router.include_router(trigger.router)
api_router.include_router(regops.router, prefix="/api/v1")
api_router.include_router(devrev_webhook.router, prefix="/api/v1")
api_router.include_router(command_center.router, prefix="/api/v1")
api_router.include_router(console.router, prefix="/api/v1")
api_router.include_router(stream.router)
