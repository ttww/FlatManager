import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .api_routes import router as api_router
from .db import init_db
from .device_queue import get_queue_manager
from .logging_config import configure_logging
from .settings import settings

configure_logging(settings.logging_timezone)

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    openapi_url=settings.openapi_url,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.on_event("shutdown")
def on_shutdown() -> None:
    # Wake long-poll waiters so shutdown does not block on poll timeout.
    get_queue_manager().notify_all()


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
