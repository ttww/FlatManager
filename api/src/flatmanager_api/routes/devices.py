# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

@router.post(
    "/admin/devices",
    response_model=AdminDeviceCreateResponse,
    tags=["devices"],
    summary="Create device",
    description=(
        "Registers a new hardware device for an apartment and returns its initial bearer token."
    ),
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
    tags=["devices"],
    summary="List devices",
    description=(
        "Returns registered devices with apartment, status, and last-seen "
        "metadata. Optional apartment filter."
    ),
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
    tags=["devices"],
    summary="Rotate device token",
    description=(
        "Invalidates the current device bearer token and issues a new one for the given device."
    ),
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
    tags=["devices"],
    summary="Update device",
    description="Updates mutable device fields such as apartment assignment or device name.",
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
    tags=["devices"],
    summary="Delete device",
    description="Deletes a registered device and removes it from future command delivery.",
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
                AccessLog.apartment_id == apartment_id,
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

    window_start = utc_now().timestamp() - settings.lockout_window_seconds
    window_start_dt = datetime.fromtimestamp(window_start, UTC)

    failed_by_ip = int(
        session.exec(
            select(func.count(AccessLog.id)).where(
                AccessLog.timestamp >= window_start_dt,
                AccessLog.ip_address == ip_address,
                AccessLog.apartment_id == apartment_id,
                AccessLog.result == "denied",
                AccessLog.reason == "validation_failed",
            )
        ).one()
    )

    failed_by_apartment = int(
        session.exec(
            select(func.count(AccessLog.id)).where(
                AccessLog.timestamp >= window_start_dt,
                AccessLog.apartment_id == apartment_id,
                AccessLog.result == "denied",
                AccessLog.reason == "validation_failed",
            )
        ).one()
    )

    return (
        failed_attempts >= settings.lockout_failed_attempts_threshold
        or failed_by_ip >= settings.lockout_ip_failed_attempts_threshold
        or failed_by_apartment >= settings.lockout_apartment_failed_attempts_threshold
    )


def is_retry_too_fast(session: Session, *, apartment_id: str, ip_address: str) -> bool:
    recent_failures = count_guest_attempts(
        session,
        apartment_id=apartment_id,
        ip_address=ip_address,
        window_seconds=settings.lockout_window_seconds,
        result="denied",
        reason="validation_failed",
    )
    if recent_failures < settings.guest_min_retry_failures_threshold:
        return False

    latest_failure = session.exec(
        select(AccessLog)
        .where(
            AccessLog.apartment_id == apartment_id,
            AccessLog.ip_address == ip_address,
            AccessLog.result == "denied",
            AccessLog.reason == "validation_failed",
        )
        .order_by(AccessLog.timestamp.desc())
    ).first()
    if latest_failure is None:
        return False

    elapsed = (utc_now() - as_utc(latest_failure.timestamp)).total_seconds()
    return elapsed < settings.guest_min_retry_interval_seconds


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


def fetch_oldest_pending_command(session: Session, *, device_id: int) -> DoorCommand | None:
    """Fetch oldest non-expired pending command for device."""
    now = utc_now()
    command = session.exec(
        select(DoorCommand)
        .where(
            DoorCommand.device_id == device_id,
            DoorCommand.status == "pending",
            DoorCommand.expires_at >= now,
        )
        .order_by(DoorCommand.created_at.asc())
    ).first()
    return command


def try_claim_command(session: Session, *, command_id: int, device_id: int) -> DoorCommand | None:
    """
    Atomically claim a command by transitioning pending -> delivered.

    Returns the claimed command if successful, None if already claimed or not found.
    """
    now = utc_now()
    command = session.exec(
        select(DoorCommand).where(
            DoorCommand.id == command_id,
            DoorCommand.device_id == device_id,
            DoorCommand.status == "pending",
        )
    ).first()

    if command is None:
        return None

    command.status = "delivered"
    command.delivered_at = now
    session.add(command)
    session.commit()
    session.refresh(command)
    return command

@router.get(
    "/admin/devices/status",
    response_model=list[DeviceStatusResponse],
    tags=["devices"],
    summary="List device status",
    description="Returns online/offline status and heartbeat details for registered devices.",
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
