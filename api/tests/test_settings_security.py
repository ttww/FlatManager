import pytest

from flatmanager_api.settings import (
    DEFAULT_ADMIN_TOKEN,
    DEFAULT_SECURITY_PEPPER,
    Settings,
)


def test_production_rejects_default_admin_token() -> None:
    with pytest.raises(ValueError, match="ADMIN_TOKEN"):
        Settings(
            app_env="production",
            admin_token=DEFAULT_ADMIN_TOKEN,
            security_pepper="custom-pepper",
        )


def test_production_rejects_default_security_pepper() -> None:
    with pytest.raises(ValueError, match="SECURITY_PEPPER"):
        Settings(
            app_env="production",
            admin_token="custom-admin-token",
            security_pepper=DEFAULT_SECURITY_PEPPER,
        )


def test_development_allows_default_secrets() -> None:
    settings = Settings(
        app_env="development",
        admin_token=DEFAULT_ADMIN_TOKEN,
        security_pepper=DEFAULT_SECURITY_PEPPER,
    )

    assert settings.admin_token == DEFAULT_ADMIN_TOKEN
    assert settings.security_pepper == DEFAULT_SECURITY_PEPPER
