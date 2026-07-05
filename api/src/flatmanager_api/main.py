from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .db import init_db
from .device_queue import get_queue_manager
from .logging_config import configure_logging
from .routes import router as api_router
from .settings import settings

configure_logging(settings.logging_timezone)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    try:
        yield
    finally:
        # Wake long-poll waiters so shutdown does not block on poll timeout.
        get_queue_manager().notify_all()


openapi_tags = [
    {
        "name": "apartments",
        "description": "Apartment configuration, timezone settings, and guest background assets.",
    },
    {
        "name": "devices",
        "description": "Admin device provisioning, token rotation, updates, and status views.",
    },
    {
        "name": "access_codes",
        "description": "Admin management of guest access codes and validity windows.",
    },
    {
        "name": "commands",
        "description": "Door command lifecycle, recent command views, and manual command actions.",
    },
    {
        "name": "access_logs",
        "description": "Audit log retrieval and maintenance operations for access events.",
    },
    {
        "name": "guest",
        "description": "Guest-facing endpoints for opening doors and polling command status.",
    },
    {
        "name": "device_agent",
        "description": "Device-authenticated long-poll and command result reporting endpoints.",
    },
    {"name": "system", "description": "Service health and system endpoints."},
]

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    openapi_url=settings.openapi_url,
    openapi_tags=openapi_tags,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "flatmanager-api"}


def cli() -> None:
    uvicorn.run(
        "flatmanager_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    cli()
