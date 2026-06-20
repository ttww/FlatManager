from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

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
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
