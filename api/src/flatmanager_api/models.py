from datetime import UTC, datetime, timedelta

from sqlmodel import Field, SQLModel

from .settings import settings


def default_command_expiration() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=settings.command_expiration_seconds)


class AccessCode(SQLModel, table=True):
    __tablename__ = "access_codes"

    id: int | None = Field(default=None, primary_key=True)
    apartment_id: str = Field(index=True, max_length=100)
    code_hash: str = Field(max_length=255)
    valid_from: datetime = Field(index=True)
    valid_until: datetime = Field(index=True)
    max_uses: int = Field(default=20)
    used_count: int = Field(default=0)
    active: bool = Field(default=True, index=True)
    booking_reference: str | None = Field(default=None, max_length=120)
    guest_name: str | None = Field(default=None, max_length=120)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: int | None = Field(default=None, primary_key=True)
    apartment_id: str = Field(index=True, max_length=100)
    device_name: str = Field(max_length=100)
    device_token_hash: str = Field(unique=True, index=True, max_length=255)
    last_seen: datetime | None = Field(default=None, index=True)
    last_ip: str | None = Field(default=None, max_length=64)
    online_status: str | None = Field(default=None, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DoorCommand(SQLModel, table=True):
    __tablename__ = "door_commands"

    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id", index=True)
    apartment_id: str = Field(index=True, max_length=100)
    command: str = Field(default="open", max_length=32)
    duration_ms: int = Field(default=1500)
    status: str = Field(default="pending", index=True, max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=default_command_expiration, index=True)
    delivered_at: datetime | None = Field(default=None)
    acknowledged_at: datetime | None = Field(default=None)
    source: str = Field(default="guest", max_length=64)
    access_code_id: int | None = Field(default=None, foreign_key="access_codes.id")


class AccessLog(SQLModel, table=True):
    __tablename__ = "access_log"

    id: int | None = Field(default=None, primary_key=True)
    apartment_id: str = Field(index=True, max_length=100)
    access_code_id: int | None = Field(default=None, foreign_key="access_codes.id")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    ip_address: str = Field(max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)
    result: str = Field(index=True, max_length=32)
    reason: str | None = Field(default=None, max_length=255)
    command_id: int | None = Field(default=None, foreign_key="door_commands.id")
