from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "data" / "flatmanager.db"


class Settings(BaseSettings):
    app_name: str = Field(default="FlatManager API")
    app_env: str = Field(default="development")
    app_debug: bool = Field(default=True)

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    database_url: str = Field(default=f"sqlite:///{DEFAULT_DB_PATH}")

    security_pepper: str = Field(default="flatmanager-dev-change-me")
    code_hash_algorithm: str = Field(default="sha256")
    token_hash_algorithm: str = Field(default="sha256")

    admin_token: str = Field(default="flatmanager-admin-dev-token")

    command_expiration_seconds: int = Field(default=10)
    default_open_duration_ms: int = Field(default=1500)

    long_poll_timeout_seconds: int = Field(default=60)
    long_poll_poll_interval_ms: int = Field(default=250)

    device_online_threshold_seconds: int = Field(default=90)

    cors_allowed_origins: list[str] = Field(
        default=[
            "http://localhost:8080",
            "http://localhost:8081",
            "http://localhost:5173",
            "http://localhost:5174",
        ]
    )

    rate_limit_window_seconds: int = Field(default=300)
    rate_limit_ip_max_attempts: int = Field(default=20)
    rate_limit_apartment_max_attempts: int = Field(default=50)

    lockout_window_seconds: int = Field(default=600)
    lockout_failed_attempts_threshold: int = Field(default=5)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
