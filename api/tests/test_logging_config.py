import logging
from datetime import UTC, datetime

import pytest

from flatmanager_api.logging_config import TimezoneAwareFormatter
from flatmanager_api.settings import Settings


def test_timezone_aware_formatter_uses_configured_timezone() -> None:
    formatter = TimezoneAwareFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %z",
        timezone_name="Europe/Berlin",
    )
    record = logging.LogRecord(
        name="flatmanager.tests",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.created = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC).timestamp()

    rendered = formatter.format(record)

    assert "2026-01-15 11:00:00 +0100" in rendered
    assert "hello" in rendered


def test_settings_reject_invalid_logging_timezone() -> None:
    with pytest.raises(ValueError, match="Invalid logging timezone"):
        Settings(logging_timezone="Mars/Olympus")
