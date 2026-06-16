"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import init_db, shutdown_db
from app.core.logging import configure_logging
from app.scheduler.jobs import start_scheduler, stop_scheduler

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()
    shutdown_db()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)

_static = Path(__file__).resolve().parent / "static" / "command-center"
if _static.is_dir():
    app.mount("/command-center/static", StaticFiles(directory=str(_static)), name="cc-static")


@app.get("/")
def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "command_center": "/command-center",
    }


@app.get("/command-center")
def command_center_ui():
    index = _static / "index.html"
    if index.is_file():
        return FileResponse(index)
    return RedirectResponse(url="/docs")
