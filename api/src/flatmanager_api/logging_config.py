import logging
from datetime import datetime
from zoneinfo import ZoneInfo


class TimezoneAwareFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: str, timezone_name: str) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._timezone = ZoneInfo(timezone_name)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=self._timezone)
        if datefmt:
            return timestamp.strftime(datefmt)
        return timestamp.isoformat(timespec="seconds")


def configure_logging(timezone_name: str) -> None:
    formatter = TimezoneAwareFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %z",
        timezone_name=timezone_name,
    )

    logger_names = [
        "",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy",
        "alembic",
    ]

    handlers_configured = False
    for logger_name in logger_names:
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            handler.setFormatter(formatter)
            handlers_configured = True

    if not handlers_configured:
        root_logger = logging.getLogger()
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    root_logger = logging.getLogger()
    if root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.INFO)
