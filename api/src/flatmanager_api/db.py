import asyncio
from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .settings import settings


def _ensure_sqlite_storage_dir() -> None:
    if settings.database_url.startswith("sqlite:///"):
        db_file = settings.database_url.replace("sqlite:///", "", 1)
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_engine():
    _ensure_sqlite_storage_dir()
    return create_engine(settings.database_url, echo=False)


def reset_engine_cache() -> None:
    get_engine.cache_clear()


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _ensure_schema_compatibility(engine)


def _ensure_schema_compatibility(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "apartments" not in table_names:
        return

    column_names = {
        column_info["name"] for column_info in inspector.get_columns("apartments")
    }

    with engine.begin() as connection:
        if "guest_background_filename" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN guest_background_filename VARCHAR(255)"
                )
            )

        if "guest_background_updated_at" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN guest_background_updated_at DATETIME"
                )
            )

        if "address_line1" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN address_line1 VARCHAR(160)"
                )
            )

        if "address_line2" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN address_line2 VARCHAR(160)"
                )
            )

        if "postal_code" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN postal_code VARCHAR(32)"
                )
            )

        if "city" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN city VARCHAR(120)"
                )
            )

        if "country_code" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN country_code VARCHAR(2)"
                )
            )

        if "latitude" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN latitude FLOAT"
                )
            )

        if "longitude" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN longitude FLOAT"
                )
            )

        if "guest_background_image_id" not in column_names:
            connection.execute(
                text(
                    "ALTER TABLE apartments "
                    "ADD COLUMN guest_background_image_id INTEGER"
                )
            )

    if "apartment_images" not in table_names:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE apartment_images (
                        id INTEGER PRIMARY KEY,
                        apartment_id VARCHAR(100) NOT NULL,
                        storage_filename VARCHAR(255) NOT NULL UNIQUE,
                        original_filename VARCHAR(255) NOT NULL,
                        content_type VARCHAR(64) NOT NULL,
                        byte_size INTEGER NOT NULL DEFAULT 0,
                        sha256 VARCHAR(64) NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(apartment_id) REFERENCES apartments(apartment_id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_apartment_images_apartment_id "
                    "ON apartment_images(apartment_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_apartment_images_sort_order "
                    "ON apartment_images(sort_order)"
                )
            )


async def get_session() -> AsyncGenerator[Session, None]:
    session = Session(get_engine())
    try:
        yield session
    finally:
        try:
            # During shutdown, request tasks may be cancelled while dependencies unwind.
            # Shield close() so this teardown does not surface cancellation tracebacks.
            await asyncio.shield(asyncio.to_thread(session.close))
        except asyncio.CancelledError:
            pass
