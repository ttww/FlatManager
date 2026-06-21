from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GuestOpenRequest(BaseModel):
    apartment_id: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=4, max_length=12)


class GuestOpenResponse(BaseModel):
    status: str
    message: str


class WaitCommandResponse(BaseModel):
    command: str
    command_id: int | None = None
    duration_ms: int | None = None
    expires_at: datetime | None = None


class CommandResultRequest(BaseModel):
    command_id: int
    status: str
    message: str | None = None


class CommandResultResponse(BaseModel):
    status: str
    message: str


class DeviceStatusResponse(BaseModel):
    id: int
    apartment_id: str
    device_name: str
    status: str
    last_seen: datetime | None
    last_seen_seconds_ago: int | None
    last_ip: str | None


class AdminDeviceCreateRequest(BaseModel):
    apartment_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=100)


class AdminDeviceCreateResponse(BaseModel):
    id: int
    apartment_id: str
    device_name: str
    raw_token: str
    created_at: datetime


class AdminDeviceSummaryResponse(BaseModel):
    id: int
    apartment_id: str
    device_name: str
    status: str
    last_seen: datetime | None
    last_ip: str | None
    created_at: datetime
    updated_at: datetime


class AdminRotateTokenResponse(BaseModel):
    id: int
    raw_token: str
    updated_at: datetime


class CommandSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apartment_id: str
    device_id: int
    command: str
    status: str
    duration_ms: int
    created_at: datetime
    expires_at: datetime
    delivered_at: datetime | None
    acknowledged_at: datetime | None


class AccessLogSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apartment_id: str
    timestamp: datetime
    ip_address: str
    result: str
    reason: str | None
    command_id: int | None


class AdminAccessCodeCreateRequest(BaseModel):
    apartment_id: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=4, max_length=12)
    valid_from: datetime
    valid_until: datetime
    max_uses: int = Field(default=20, ge=1, le=10000)
    booking_reference: str | None = Field(default=None, max_length=120)
    guest_name: str | None = Field(default=None, max_length=120)


class AdminAccessCodeUpdateRequest(BaseModel):
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1, le=10000)
    booking_reference: str | None = None
    guest_name: str | None = None
    active: bool | None = None


class AdminAccessCodeSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apartment_id: str
    valid_from: datetime
    valid_until: datetime
    max_uses: int
    used_count: int
    active: bool
    booking_reference: str | None
    guest_name: str | None
    created_at: datetime
    updated_at: datetime


class AdminManualOpenRequest(BaseModel):
    apartment_id: str = Field(min_length=1, max_length=100)
    duration_ms: int | None = Field(default=None, ge=100, le=10000)


class AdminManualOpenResponse(BaseModel):
    status: str
    message: str
    command_id: int
    apartment_id: str
    device_id: int
