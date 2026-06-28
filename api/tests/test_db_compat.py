from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

from flatmanager_api.db import get_engine, init_db, reset_engine_cache
from flatmanager_api.settings import settings


def test_init_db_adds_missing_apartment_background_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    settings.database_url = f"sqlite:///{db_path}"
    reset_engine_cache()

    with Session(get_engine()) as session:
        session.exec(
            text(
                """
            CREATE TABLE apartments (
                id INTEGER PRIMARY KEY,
                apartment_id VARCHAR(100) NOT NULL UNIQUE,
                timezone VARCHAR(100) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
            )
        )
        session.commit()

    init_db()

    with Session(get_engine()) as session:
        rows = session.exec(text("PRAGMA table_info(apartments)")).all()
        column_names = {row[1] for row in rows}

    assert "guest_background_filename" in column_names
    assert "guest_background_updated_at" in column_names
