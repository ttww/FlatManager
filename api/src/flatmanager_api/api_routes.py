import hashlib
import logging
import time
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func
from sqlmodel import Session, select

from .db import get_session
from .models import AccessCode, AccessLog, Apartment, Device, DoorCommand
from .schemas import (
    AccessLogSummaryResponse,
    AdminAccessCodeCreateRequest,
    AdminAccessCodeSummaryResponse,
    AdminAccessCodeUpdateRequest,
    AdminApartmentCreateRequest,
    AdminApartmentTimezoneSummaryResponse,
    AdminApartmentTimezoneUpdateRequest,
    AdminDeviceCreateRequest,
    AdminDeviceCreateResponse,
    AdminDeviceSummaryResponse,
    AdminDeviceUpdateRequest,
    AdminManualOpenRequest,
    AdminManualOpenResponse,
    AdminRotateTokenResponse,
    CommandResultRequest,
    CommandResultResponse,
    CommandSummaryResponse,
    DeviceStatusResponse,
    GuestOpenRequest,
    GuestOpenResponse,
    WaitCommandResponse,
)
from .security import hash_access_code, hash_device_token
from .settings import settings

router = APIRouter(prefix="/api")
device_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

NEUTRAL_DENIED_MESSAGE = "Code invalid or not valid."
SUCCESS_MESSAGE = "Door opening requested."


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def derive_device_status(last_seen: datetime | None) -> str:
    normalized = as_utc(last_seen)
    if normalized is None:
        return "offline"

    delta = utc_now() - normalized
    if delta.total_seconds() < settings.device_online_threshold_seconds:
        return "online"
    return "offline"


def validate_timezone_name(timezone_name: str) -> str:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone '{timezone_name}'. Use IANA timezone names like Europe/Berlin.",
        ) from error

    return timezone_name


def normalize_datetime_to_utc(value: datetime, *, input_timezone: str | None = None) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC)

    timezone_name = input_timezone or "UTC"
    normalized_timezone = validate_timezone_name(timezone_name)
    localized = value.replace(tzinfo=ZoneInfo(normalized_timezone))
    return localized.astimezone(UTC)


def get_apartment_or_404(session: Session, apartment_id: str) -> Apartment:
    apartment = session.exec(
        select(Apartment).where(Apartment.apartment_id == apartment_id)
    ).first()
    if apartment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Apartment not found")
    return apartment


def get_apartment_timezone_map(session: Session, apartment_ids: set[str]) -> dict[str, str]:
    if not apartment_ids:
        return {}

    apartments = session.exec(
        select(Apartment).where(Apartment.apartment_id.in_(list(apartment_ids)))
    ).all()
    return {apartment.apartment_id: apartment.timezone for apartment in apartments}


def apartment_timezone_for(apartment_id: str, timezone_map: dict[str, str]) -> str:
    return timezone_map.get(apartment_id, "UTC")


def command_to_summary(command: DoorCommand, apartment_timezone: str) -> CommandSummaryResponse:
    return CommandSummaryResponse(
        id=command.id,
        apartment_id=command.apartment_id,
        apartment_timezone=apartment_timezone,
        device_id=command.device_id,
        command=command.command,
        status=command.status,
        duration_ms=command.duration_ms,
        created_at=command.created_at,
        expires_at=command.expires_at,
        delivered_at=command.delivered_at,
        acknowledged_at=command.acknowledged_at,
    )


def access_log_to_summary(
    access_log: AccessLog, apartment_timezone: str
) -> AccessLogSummaryResponse:
    return AccessLogSummaryResponse(
        id=access_log.id,
        apartment_id=access_log.apartment_id,
        apartment_timezone=apartment_timezone,
        timestamp=access_log.timestamp,
        ip_address=access_log.ip_address,
        result=access_log.result,
        reason=access_log.reason,
        command_id=access_log.command_id,
    )


def access_code_to_summary(
    access_code: AccessCode, apartment_timezone: str
) -> AdminAccessCodeSummaryResponse:
    return AdminAccessCodeSummaryResponse(
        id=access_code.id,
        apartment_id=access_code.apartment_id,
        apartment_timezone=apartment_timezone,
        valid_from=access_code.valid_from,
        valid_until=access_code.valid_until,
        max_uses=access_code.max_uses,
        used_count=access_code.used_count,
        active=access_code.active,
        booking_reference=access_code.booking_reference,
        guest_name=access_code.guest_name,
        created_at=access_code.created_at,
        updated_at=access_code.updated_at,
    )


def device_to_summary(device: Device, apartment_timezone: str) -> AdminDeviceSummaryResponse:
    return AdminDeviceSummaryResponse(
        id=device.id,
        apartment_id=device.apartment_id,
        apartment_timezone=apartment_timezone,
        device_name=device.device_name,
        status=derive_device_status(device.last_seen),
        last_seen=device.last_seen,
        last_ip=device.last_ip,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def require_admin_token(
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


def token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:12]


@router.get(
    "/admin/apartments",
    response_model=list[AdminApartmentTimezoneSummaryResponse],
    dependencies=[Depends(require_admin_token)],
)
def admin_list_apartments(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
) -> list[AdminApartmentTimezoneSummaryResponse]:
    query = select(Apartment).order_by(Apartment.apartment_id.asc())
    if apartment_id:
        query = query.where(Apartment.apartment_id == apartment_id)

    return [
        AdminApartmentTimezoneSummaryResponse(
            apartment_id=apartment.apartment_id,
            timezone=apartment.timezone,
        )
        for apartment in session.exec(query).all()
    ]


@router.get(
    "/admin/apartments/{apartment_id}",
    response_model=AdminApartmentTimezoneSummaryResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_get_apartment(
    apartment_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    return AdminApartmentTimezoneSummaryResponse(
        apartment_id=apartment.apartment_id,
        timezone=apartment.timezone,
    )


@router.post(
    "/admin/apartments",
    response_model=AdminApartmentTimezoneSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
def admin_create_apartment(
    payload: AdminApartmentCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    existing = session.exec(
        select(Apartment).where(Apartment.apartment_id == payload.apartment_id)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Apartment already exists")

    timezone_name = validate_timezone_name(payload.timezone)
    now = utc_now()
    apartment = Apartment(
        apartment_id=payload.apartment_id,
        timezone=timezone_name,
        created_at=now,
        updated_at=now,
    )
    session.add(apartment)
    session.commit()
    session.refresh(apartment)

    return AdminApartmentTimezoneSummaryResponse(
        apartment_id=apartment.apartment_id,
        timezone=apartment.timezone,
    )


@router.put(
    "/admin/apartments/{apartment_id}/timezone",
    response_model=AdminApartmentTimezoneSummaryResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_update_apartment_timezone(
    apartment_id: str,
    payload: AdminApartmentTimezoneUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    timezone_name = validate_timezone_name(payload.timezone)
    apartment = get_apartment_or_404(session, apartment_id)
    apartment.timezone = timezone_name
    apartment.updated_at = utc_now()
    session.add(apartment)
    session.commit()

    return AdminApartmentTimezoneSummaryResponse(
        apartment_id=apartment.apartment_id,
        timezone=apartment.timezone,
    )


@router.delete(
    "/admin/apartments/{apartment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_apartment(
    apartment_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    apartment = get_apartment_or_404(session, apartment_id)

    has_devices = session.exec(
        select(Device.id).where(Device.apartment_id == apartment_id).limit(1)
    ).first()
    if has_devices is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete apartment with existing devices.",
        )

    has_access_codes = session.exec(
        select(AccessCode.id).where(AccessCode.apartment_id == apartment_id).limit(1)
    ).first()
    if has_access_codes is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete apartment with existing access codes.",
        )

    session.delete(apartment)
    session.commit()


def get_current_device(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(device_bearer)],
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Device:
    if credentials is None:
        logger.warning(
            "Device auth failed: missing bearer token path=%s ip=%s ua=%s",
            request.url.path,
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", "-"),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token_hash = hash_device_token(credentials.credentials)
    device = session.exec(select(Device).where(Device.device_token_hash == token_hash)).first()

    if device is None:
        logger.warning(
            "Device auth failed: invalid bearer token path=%s ip=%s token_fp=%s ua=%s",
            request.url.path,
            request.client.host if request.client else "unknown",
            token_fingerprint(credentials.credentials),
            request.headers.get("user-agent", "-"),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    return device


@router.post(
    "/admin/devices",
    response_model=AdminDeviceCreateResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_create_device(
    payload: AdminDeviceCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminDeviceCreateResponse:
    raw_token = token_urlsafe(32)
    token_hash = hash_device_token(raw_token)
    now = utc_now()
    get_apartment_or_404(session, payload.apartment_id)

    device = Device(
        apartment_id=payload.apartment_id,
        device_name=payload.device_name,
        device_token_hash=token_hash,
        created_at=now,
        updated_at=now,
    )
    session.add(device)
    session.commit()
    session.refresh(device)

    return AdminDeviceCreateResponse(
        id=device.id,
        apartment_id=device.apartment_id,
        device_name=device.device_name,
        raw_token=raw_token,
        created_at=device.created_at,
    )


@router.get(
    "/admin/devices",
    response_model=list[AdminDeviceSummaryResponse],
    dependencies=[Depends(require_admin_token)],
)
def admin_list_devices(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
) -> list[AdminDeviceSummaryResponse]:
    query = select(Device).order_by(Device.apartment_id.asc(), Device.device_name.asc())
    if apartment_id:
        query = query.where(Device.apartment_id == apartment_id)

    devices = session.exec(query).all()
    timezone_map = get_apartment_timezone_map(
        session,
        {device.apartment_id for device in devices},
    )

    return [
        device_to_summary(device, apartment_timezone_for(device.apartment_id, timezone_map))
        for device in devices
    ]


@router.post(
    "/admin/devices/{device_id}/rotate-token",
    response_model=AdminRotateTokenResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_rotate_device_token(
    device_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> AdminRotateTokenResponse:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    raw_token = token_urlsafe(32)
    device.device_token_hash = hash_device_token(raw_token)
    device.updated_at = utc_now()

    session.add(device)
    session.commit()
    session.refresh(device)

    return AdminRotateTokenResponse(id=device.id, raw_token=raw_token, updated_at=device.updated_at)


@router.patch(
    "/admin/devices/{device_id}",
    response_model=AdminDeviceSummaryResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_update_device(
    device_id: int,
    payload: AdminDeviceUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminDeviceSummaryResponse:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "apartment_id" in update_data and update_data["apartment_id"] is not None:
        get_apartment_or_404(session, update_data["apartment_id"])

    for field, value in update_data.items():
        setattr(device, field, value)

    device.updated_at = utc_now()
    session.add(device)
    session.commit()
    session.refresh(device)

    timezone_map = get_apartment_timezone_map(session, {device.apartment_id})
    return device_to_summary(device, apartment_timezone_for(device.apartment_id, timezone_map))


@router.delete(
    "/admin/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_device(
    device_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    session.delete(device)
    session.commit()


def log_access_event(
    session: Session,
    *,
    apartment_id: str,
    ip_address: str,
    result: str,
    reason: str | None = None,
    access_code_id: int | None = None,
    command_id: int | None = None,
    user_agent: str | None = None,
) -> None:
    session.add(
        AccessLog(
            apartment_id=apartment_id,
            access_code_id=access_code_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result=result,
            reason=reason,
            command_id=command_id,
            timestamp=utc_now(),
        )
    )


def count_guest_attempts(
    session: Session,
    *,
    apartment_id: str,
    ip_address: str,
    window_seconds: int,
    result: str | None = None,
    reason: str | None = None,
) -> int:
    window_start = utc_now().timestamp() - window_seconds
    window_start_dt = datetime.fromtimestamp(window_start, UTC)

    query = select(func.count(AccessLog.id)).where(
        AccessLog.timestamp >= window_start_dt,
        AccessLog.apartment_id == apartment_id,
        AccessLog.ip_address == ip_address,
    )

    if result is not None:
        query = query.where(AccessLog.result == result)

    if reason is not None:
        query = query.where(AccessLog.reason == reason)

    return int(session.exec(query).one())


def is_rate_limited(session: Session, *, apartment_id: str, ip_address: str) -> bool:
    window_start = utc_now().timestamp() - settings.rate_limit_window_seconds
    window_start_dt = datetime.fromtimestamp(window_start, UTC)

    ip_attempts = int(
        session.exec(
            select(func.count(AccessLog.id)).where(
                AccessLog.timestamp >= window_start_dt,
                AccessLog.ip_address == ip_address,
            )
        ).one()
    )

    apartment_attempts = int(
        session.exec(
            select(func.count(AccessLog.id)).where(
                AccessLog.timestamp >= window_start_dt,
                AccessLog.apartment_id == apartment_id,
            )
        ).one()
    )

    return (
        ip_attempts >= settings.rate_limit_ip_max_attempts
        or apartment_attempts >= settings.rate_limit_apartment_max_attempts
    )


def is_locked_out(session: Session, *, apartment_id: str, ip_address: str) -> bool:
    failed_attempts = count_guest_attempts(
        session,
        apartment_id=apartment_id,
        ip_address=ip_address,
        window_seconds=settings.lockout_window_seconds,
        result="denied",
        reason="validation_failed",
    )
    return failed_attempts >= settings.lockout_failed_attempts_threshold


def expire_pending_commands(session: Session, *, device_id: int) -> None:
    now = utc_now()
    commands = session.exec(
        select(DoorCommand).where(
            DoorCommand.device_id == device_id,
            DoorCommand.status == "pending",
            DoorCommand.expires_at < now,
        )
    ).all()
    for command in commands:
        command.status = "expired"
        command.acknowledged_at = now


@router.post("/guest/open", response_model=GuestOpenResponse)
def guest_open(
    payload: GuestOpenRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> GuestOpenResponse:
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")

    if is_rate_limited(session, apartment_id=payload.apartment_id, ip_address=ip_address):
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result="rate_limited",
            reason="rate_limit",
        )
        session.commit()
        return GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE)

    if is_locked_out(session, apartment_id=payload.apartment_id, ip_address=ip_address):
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result="denied",
            reason="lockout",
        )
        session.commit()
        return GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE)

    code_hash = hash_access_code(payload.apartment_id, payload.code)
    now = utc_now()

    access_code = session.exec(
        select(AccessCode).where(
            AccessCode.apartment_id == payload.apartment_id,
            AccessCode.code_hash == code_hash,
            AccessCode.active.is_(True),
            AccessCode.valid_from <= now,
            AccessCode.valid_until >= now,
            AccessCode.used_count < AccessCode.max_uses,
        )
    ).first()

    if access_code is None:
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result="denied",
            reason="validation_failed",
        )
        session.commit()
        return GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE)

    device = session.exec(
        select(Device).where(Device.apartment_id == payload.apartment_id).order_by(Device.id.asc())
    ).first()

    if device is None:
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            access_code_id=access_code.id,
            result="device_offline",
            reason="device_not_registered",
        )
        session.commit()
        return GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE)

    access_code.used_count += 1
    access_code.updated_at = now

    command = DoorCommand(
        device_id=device.id,
        apartment_id=payload.apartment_id,
        command="open",
        duration_ms=settings.default_open_duration_ms,
        status="pending",
        source="guest",
        access_code_id=access_code.id,
    )
    session.add(command)
    session.flush()

    log_access_event(
        session,
        apartment_id=payload.apartment_id,
        ip_address=ip_address,
        user_agent=user_agent,
        access_code_id=access_code.id,
        command_id=command.id,
        result="success",
        reason="accepted",
    )

    session.commit()
    return GuestOpenResponse(status="accepted", message=SUCCESS_MESSAGE)


@router.get("/device/wait-command", response_model=WaitCommandResponse)
def wait_command(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[Device, Depends(get_current_device)],
) -> WaitCommandResponse:
    deadline = time.monotonic() + settings.long_poll_timeout_seconds
    sleep_seconds = settings.long_poll_poll_interval_ms / 1000

    while True:
        now = utc_now()
        expire_pending_commands(session, device_id=device.id)

        device.last_seen = now
        device.updated_at = now
        device.last_ip = request.client.host if request.client else None
        device.online_status = "online"

        command = session.exec(
            select(DoorCommand)
            .where(
                DoorCommand.device_id == device.id,
                DoorCommand.status == "pending",
            )
            .order_by(DoorCommand.created_at.asc())
        ).first()

        if command is not None:
            expires_at = as_utc(command.expires_at)
            if expires_at is not None and expires_at <= now:
                command.status = "expired"
                command.acknowledged_at = now
                session.commit()
            else:
                command.status = "delivered"
                command.delivered_at = now
                session.commit()
                return WaitCommandResponse(
                    command_id=command.id,
                    command=command.command,
                    duration_ms=command.duration_ms,
                    expires_at=command.expires_at,
                )
        else:
            session.commit()

        if time.monotonic() >= deadline:
            return WaitCommandResponse(command="none")

        time.sleep(sleep_seconds)


@router.post("/device/command-result", response_model=CommandResultResponse)
def command_result(
    payload: CommandResultRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[Device, Depends(get_current_device)],
) -> CommandResultResponse:
    status_value = payload.status.lower()
    valid_statuses = {"done", "failed", "expired", "ignored"}
    if status_value not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

    command = session.exec(
        select(DoorCommand).where(
            DoorCommand.id == payload.command_id,
            DoorCommand.device_id == device.id,
        )
    ).first()

    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")

    now = utc_now()
    expires_at = as_utc(command.expires_at)

    if expires_at is not None and expires_at < now and status_value == "done":
        command.status = "expired"
    else:
        command.status = status_value

    command.acknowledged_at = now

    ip_address = request.client.host if request.client else "unknown"
    result_map = {
        "done": "success",
        "failed": "failed",
        "expired": "expired",
        "ignored": "denied",
    }

    log_access_event(
        session,
        apartment_id=command.apartment_id,
        ip_address=ip_address,
        result=result_map[command.status],
        reason=payload.message,
        command_id=command.id,
        access_code_id=command.access_code_id,
        user_agent=request.headers.get("user-agent"),
    )

    session.commit()
    return CommandResultResponse(status="accepted", message="Command result processed")


@router.get(
    "/admin/devices/status",
    response_model=list[DeviceStatusResponse],
    dependencies=[Depends(require_admin_token)],
)
def admin_devices_status(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
) -> list[DeviceStatusResponse]:
    query = select(Device).order_by(Device.apartment_id.asc(), Device.device_name.asc())
    if apartment_id:
        query = query.where(Device.apartment_id == apartment_id)

    devices = session.exec(query).all()
    timezone_map = get_apartment_timezone_map(
        session,
        {device.apartment_id for device in devices},
    )
    rows: list[DeviceStatusResponse] = []

    for device in devices:
        normalized_last_seen = as_utc(device.last_seen)
        seconds_ago = None
        if normalized_last_seen is not None:
            seconds_ago = int((utc_now() - normalized_last_seen).total_seconds())

        rows.append(
            DeviceStatusResponse(
                id=device.id,
                apartment_id=device.apartment_id,
                apartment_timezone=apartment_timezone_for(device.apartment_id, timezone_map),
                device_name=device.device_name,
                status=derive_device_status(device.last_seen),
                last_seen=device.last_seen,
                last_seen_seconds_ago=seconds_ago,
                last_ip=device.last_ip,
            )
        )

    return rows


@router.get(
    "/admin/commands/recent",
    response_model=list[CommandSummaryResponse],
    dependencies=[Depends(require_admin_token)],
)
def admin_recent_commands(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
    limit: int = 100,
) -> list[CommandSummaryResponse]:
    safe_limit = max(1, min(limit, 500))
    query = select(DoorCommand).order_by(DoorCommand.created_at.desc()).limit(safe_limit)
    if apartment_id:
        query = query.where(DoorCommand.apartment_id == apartment_id)

    commands = session.exec(query).all()
    timezone_map = get_apartment_timezone_map(
        session,
        {command.apartment_id for command in commands},
    )

    return [
        command_to_summary(command, apartment_timezone_for(command.apartment_id, timezone_map))
        for command in commands
    ]


@router.get(
    "/admin/access-logs/recent",
    response_model=list[AccessLogSummaryResponse],
    dependencies=[Depends(require_admin_token)],
)
def admin_recent_access_logs(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
    limit: int = 200,
) -> list[AccessLogSummaryResponse]:
    safe_limit = max(1, min(limit, 1000))
    query = select(AccessLog).order_by(AccessLog.timestamp.desc()).limit(safe_limit)
    if apartment_id:
        query = query.where(AccessLog.apartment_id == apartment_id)

    logs = session.exec(query).all()
    timezone_map = get_apartment_timezone_map(
        session,
        {log_row.apartment_id for log_row in logs},
    )

    return [
        access_log_to_summary(log_row, apartment_timezone_for(log_row.apartment_id, timezone_map))
        for log_row in logs
    ]


@router.delete(
    "/admin/commands",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_all_commands(
    session: Annotated[Session, Depends(get_session)],
) -> None:
    for command in session.exec(select(DoorCommand)).all():
        session.delete(command)
    session.commit()


@router.delete(
    "/admin/access-logs",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_all_access_logs(
    session: Annotated[Session, Depends(get_session)],
) -> None:
    for log_row in session.exec(select(AccessLog)).all():
        session.delete(log_row)
    session.commit()


@router.post(
    "/admin/commands/manual-open",
    response_model=AdminManualOpenResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_manual_open(
    payload: AdminManualOpenRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AdminManualOpenResponse:
    get_apartment_or_404(session, payload.apartment_id)
    device = session.exec(
        select(Device).where(Device.apartment_id == payload.apartment_id).order_by(Device.id.asc())
    ).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    duration_ms = payload.duration_ms or settings.default_open_duration_ms
    command = DoorCommand(
        device_id=device.id,
        apartment_id=payload.apartment_id,
        command="open",
        duration_ms=duration_ms,
        status="pending",
        source="admin_manual",
        access_code_id=None,
    )
    session.add(command)
    session.flush()

    ip_address = request.client.host if request.client else "unknown"
    log_access_event(
        session,
        apartment_id=payload.apartment_id,
        ip_address=ip_address,
        result="success",
        reason="manual_open_requested",
        command_id=command.id,
        access_code_id=None,
        user_agent=request.headers.get("user-agent"),
    )

    session.commit()
    return AdminManualOpenResponse(
        status="accepted",
        message="Manual open command submitted.",
        command_id=command.id,
        apartment_id=payload.apartment_id,
        device_id=device.id,
    )


@router.get(
    "/admin/access-codes",
    response_model=list[AdminAccessCodeSummaryResponse],
    dependencies=[Depends(require_admin_token)],
)
def admin_list_access_codes(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
) -> list[AdminAccessCodeSummaryResponse]:
    query = select(AccessCode).order_by(AccessCode.valid_until.desc())
    if apartment_id:
        query = query.where(AccessCode.apartment_id == apartment_id)
    access_codes = session.exec(query).all()
    timezone_map = get_apartment_timezone_map(
        session,
        {row.apartment_id for row in access_codes},
    )

    return [
        access_code_to_summary(row, apartment_timezone_for(row.apartment_id, timezone_map))
        for row in access_codes
    ]


@router.post(
    "/admin/access-codes",
    response_model=AdminAccessCodeSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_token)],
)
def admin_create_access_code(
    payload: AdminAccessCodeCreateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminAccessCodeSummaryResponse:
    now = utc_now()
    apartment = get_apartment_or_404(session, payload.apartment_id)
    input_timezone = payload.input_timezone or apartment.timezone
    code_hash = hash_access_code(payload.apartment_id, payload.code)
    access_code = AccessCode(
        apartment_id=payload.apartment_id,
        code_hash=code_hash,
        valid_from=normalize_datetime_to_utc(payload.valid_from, input_timezone=input_timezone),
        valid_until=normalize_datetime_to_utc(payload.valid_until, input_timezone=input_timezone),
        max_uses=payload.max_uses,
        booking_reference=payload.booking_reference,
        guest_name=payload.guest_name,
        active=True,
        used_count=0,
        created_at=now,
        updated_at=now,
    )
    session.add(access_code)
    session.commit()
    session.refresh(access_code)
    return access_code_to_summary(access_code, apartment.timezone)


@router.patch(
    "/admin/access-codes/{code_id}",
    response_model=AdminAccessCodeSummaryResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_update_access_code(
    code_id: int,
    payload: AdminAccessCodeUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminAccessCodeSummaryResponse:
    access_code = session.get(AccessCode, code_id)
    if access_code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access code not found")

    apartment = get_apartment_or_404(session, access_code.apartment_id)
    input_timezone = payload.input_timezone or apartment.timezone
    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("input_timezone", None)

    if "valid_from" in update_data and update_data["valid_from"] is not None:
        update_data["valid_from"] = normalize_datetime_to_utc(
            update_data["valid_from"],
            input_timezone=input_timezone,
        )

    if "valid_until" in update_data and update_data["valid_until"] is not None:
        update_data["valid_until"] = normalize_datetime_to_utc(
            update_data["valid_until"],
            input_timezone=input_timezone,
        )

    for field, value in update_data.items():
        setattr(access_code, field, value)
    access_code.updated_at = utc_now()

    session.add(access_code)
    session.commit()
    session.refresh(access_code)
    return access_code_to_summary(access_code, apartment.timezone)


@router.post(
    "/admin/access-codes/{code_id}/deactivate",
    response_model=AdminAccessCodeSummaryResponse,
    dependencies=[Depends(require_admin_token)],
)
def admin_deactivate_access_code(
    code_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> AdminAccessCodeSummaryResponse:
    access_code = session.get(AccessCode, code_id)
    if access_code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access code not found")

    access_code.active = False
    access_code.updated_at = utc_now()
    session.add(access_code)
    session.commit()
    session.refresh(access_code)
    timezone_map = get_apartment_timezone_map(session, {access_code.apartment_id})
    return access_code_to_summary(
        access_code,
        apartment_timezone_for(access_code.apartment_id, timezone_map),
    )


@router.delete(
    "/admin/access-codes/{code_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_access_code(
    code_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    access_code = session.get(AccessCode, code_id)
    if access_code is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access code not found")

    session.delete(access_code)
    session.commit()
