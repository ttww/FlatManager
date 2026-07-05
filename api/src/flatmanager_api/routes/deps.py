# ruff: noqa: F401

import asyncio
import hashlib
import hmac
import logging
import mimetypes
import time
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, update
from sqlmodel import Session, select

from ..db import get_session
from ..device_queue import get_queue_manager
from ..models import AccessCode, AccessLog, Apartment, ApartmentImage, Device, DoorCommand
from ..schemas import (
    AccessLogSummaryResponse,
    AdminAccessCodeCreateRequest,
    AdminAccessCodeSummaryResponse,
    AdminAccessCodeUpdateRequest,
    AdminApartmentCreateRequest,
    AdminApartmentTimezoneSummaryResponse,
    AdminApartmentTimezoneUpdateRequest,
    AdminApartmentUpdateRequest,
    AdminDeviceCreateRequest,
    AdminDeviceCreateResponse,
    AdminDeviceSummaryResponse,
    AdminDeviceUpdateRequest,
    AdminManualOpenRequest,
    AdminManualOpenResponse,
    AdminRotateTokenResponse,
    ApartmentImageBulkUploadResponse,
    ApartmentImageReorderRequest,
    ApartmentImageSummaryResponse,
    CommandResultRequest,
    CommandResultResponse,
    CommandSummaryResponse,
    DeviceStatusResponse,
    GuestBackgroundUrlResponse,
    GuestCommandStatusResponse,
    GuestOpenRequest,
    GuestOpenResponse,
    WaitCommandResponse,
)
from ..security import hash_access_code, hash_device_token
from ..settings import settings

device_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

NEUTRAL_DENIED_MESSAGE = "Code invalid or not valid."
SUCCESS_MESSAGE = "Door opening requested."
GUEST_BACKGROUND_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
GUEST_BACKGROUND_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def utc_now() -> datetime:
    return datetime.now(UTC)


def apartment_to_summary(
    apartment: Apartment,
    *,
    gallery_count: int = 0,
) -> AdminApartmentTimezoneSummaryResponse:
    return AdminApartmentTimezoneSummaryResponse(
        apartment_id=apartment.apartment_id,
        timezone=apartment.timezone,
        address_line1=apartment.address_line1,
        address_line2=apartment.address_line2,
        postal_code=apartment.postal_code,
        city=apartment.city,
        country_code=apartment.country_code,
        latitude=apartment.latitude,
        longitude=apartment.longitude,
        has_guest_background=(
            apartment.guest_background_image_id is not None
            or apartment.guest_background_filename is not None
        ),
        guest_background_image_id=apartment.guest_background_image_id,
        gallery_count=gallery_count,
    )


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
            detail=(
                f"Invalid timezone '{timezone_name}'. Use IANA timezone names like Europe/Berlin."
            ),
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
        access_code_id=access_log.access_code_id,
    )


def has_overlapping_code_window(
    session: Session,
    *,
    apartment_id: str,
    code_hash: str,
    valid_from: datetime,
    valid_until: datetime,
) -> bool:
    """Return True when same code overlaps in time for the same apartment."""
    overlapping = session.exec(
        select(AccessCode).where(
            AccessCode.apartment_id == apartment_id,
            AccessCode.code_hash == code_hash,
            AccessCode.valid_from <= valid_until,
            AccessCode.valid_until >= valid_from,
        )
    ).first()
    return overlapping is not None


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
    if not is_valid_admin_token(x_admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


def is_valid_admin_token(provided_token: str | None) -> bool:
    if not provided_token:
        return False
    return hmac.compare_digest(
        provided_token.encode("utf-8"),
        settings.admin_token.encode("utf-8"),
    )


def token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:12]


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


def guest_background_directory() -> Path:
    configured = Path(settings.guest_backgrounds_dir)
    directory = configured if configured.is_absolute() else (Path.cwd() / configured)

    try:
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()
    except PermissionError:
        if settings.database_url.startswith("sqlite:///"):
            db_file = settings.database_url.replace("sqlite:///", "", 1)
            db_path = Path(db_file)
            if not db_path.is_absolute():
                db_path = (Path.cwd() / db_path).resolve()

            fallback = db_path.parent / "guest-backgrounds"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

        raise


def apartment_gallery_directory() -> Path:
    configured = Path(settings.apartment_gallery_dir)
    directory = configured if configured.is_absolute() else (Path.cwd() / configured)

    try:
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()
    except PermissionError:
        if settings.database_url.startswith("sqlite:///"):
            db_file = settings.database_url.replace("sqlite:///", "", 1)
            db_path = Path(db_file)
            if not db_path.is_absolute():
                db_path = (Path.cwd() / db_path).resolve()

            fallback = db_path.parent / "apartment-gallery"
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

        raise


def normalized_apartment_key(apartment_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in apartment_id)


def apartment_gallery_apartment_directory(apartment_id: str) -> Path:
    apartment_dir = apartment_gallery_directory() / normalized_apartment_key(apartment_id)
    apartment_dir.mkdir(parents=True, exist_ok=True)
    return apartment_dir


def build_apartment_image_filename(apartment_id: str, extension: str) -> str:
    return f"{normalized_apartment_key(apartment_id)}-{token_urlsafe(18)}{extension}"


def apartment_image_path(apartment_image: ApartmentImage) -> Path | None:
    filename = Path(apartment_image.storage_filename).name
    candidate = (
        apartment_gallery_apartment_directory(apartment_image.apartment_id) / filename
    ).resolve()
    base = apartment_gallery_directory().resolve()
    if base not in candidate.parents and candidate != base:
        return None
    return candidate


def count_gallery_images(session: Session, apartment_ids: set[str]) -> dict[str, int]:
    if not apartment_ids:
        return {}

    rows = session.exec(
        select(ApartmentImage.apartment_id, func.count(ApartmentImage.id))
        .where(ApartmentImage.apartment_id.in_(list(apartment_ids)))
        .group_by(ApartmentImage.apartment_id)
    ).all()
    return {apartment_id: int(count) for apartment_id, count in rows}


def apartment_image_to_summary(
    apartment_image: ApartmentImage,
    *,
    request: Request,
    is_guest_background: bool,
) -> ApartmentImageSummaryResponse:
    url = str(
        request.url_for(
            "admin_get_apartment_image_file",
            apartment_id=apartment_image.apartment_id,
            image_id=apartment_image.id,
        )
    )
    return ApartmentImageSummaryResponse(
        id=apartment_image.id,
        apartment_id=apartment_image.apartment_id,
        original_filename=apartment_image.original_filename,
        content_type=apartment_image.content_type,
        byte_size=apartment_image.byte_size,
        sort_order=apartment_image.sort_order,
        image_url=url,
        is_guest_background=is_guest_background,
        created_at=apartment_image.created_at,
        updated_at=apartment_image.updated_at,
    )


def normalize_background_extension(file: UploadFile) -> str | None:
    filename = (file.filename or "").lower()
    if "." in filename:
        extension = f".{filename.rsplit('.', 1)[1]}"
        if extension in GUEST_BACKGROUND_ALLOWED_EXTENSIONS:
            if extension == ".jpeg":
                return ".jpg"
            return extension

    content_type = (file.content_type or "").lower()
    return GUEST_BACKGROUND_ALLOWED_CONTENT_TYPES.get(content_type)


def build_guest_background_filename(apartment_id: str, extension: str) -> str:
    safe_apartment = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in apartment_id)
    return f"{safe_apartment}-{token_urlsafe(18)}{extension}"


def apartment_background_path(apartment: Apartment) -> Path | None:
    if not apartment.guest_background_filename:
        return None

    filename = Path(apartment.guest_background_filename).name
    candidate = (guest_background_directory() / filename).resolve()
    base = guest_background_directory().resolve()

    if base not in candidate.parents and candidate != base:
        return None

    return candidate


def sign_guest_background(apartment_id: str, exp: int) -> str:
    payload = f"{apartment_id}:{exp}".encode()
    secret = settings.security_pepper.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_guest_background_signature(apartment_id: str, exp: int, signature: str) -> bool:
    expected = sign_guest_background(apartment_id, exp)
    return hmac.compare_digest(expected, signature)


def build_guest_background_url(request: Request, apartment_id: str) -> str:
    exp = int(time.time()) + settings.guest_background_url_ttl_seconds
    sig = sign_guest_background(apartment_id, exp)
    base_url = str(request.url_for("guest_get_background", apartment_id=apartment_id))
    return f"{base_url}?exp={exp}&sig={sig}"


async def store_apartment_gallery_image(
    session: Session,
    *,
    apartment: Apartment,
    file: UploadFile,
    set_as_guest_background: bool,
) -> tuple[ApartmentImage, bool]:
    extension = normalize_background_extension(file)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image format. Use JPG, PNG, or WEBP.",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty image file.")
    if len(payload) > settings.guest_background_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image too large.",
        )

    payload_sha256 = hashlib.sha256(payload).hexdigest()
    duplicate_image = session.exec(
        select(ApartmentImage)
        .where(ApartmentImage.apartment_id == apartment.apartment_id)
        .where(ApartmentImage.sha256 == payload_sha256)
    ).first()
    if duplicate_image is not None:
        if set_as_guest_background and apartment.guest_background_image_id != duplicate_image.id:
            now = utc_now()
            apartment.guest_background_image_id = duplicate_image.id
            apartment.guest_background_filename = None
            apartment.guest_background_updated_at = now
            apartment.updated_at = now
            session.add(apartment)
            session.commit()
        return duplicate_image, False

    image_count = int(
        session.exec(
            select(func.count(ApartmentImage.id)).where(
                ApartmentImage.apartment_id == apartment.apartment_id
            )
        ).one()
    )
    if image_count >= settings.apartment_gallery_max_images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Apartment gallery limit reached. Maximum is "
                f"{settings.apartment_gallery_max_images} images."
            ),
        )

    filename = build_apartment_image_filename(apartment.apartment_id, extension)
    target_path = apartment_gallery_apartment_directory(apartment.apartment_id) / filename
    target_path.write_bytes(payload)

    max_sort_order = session.exec(
        select(func.max(ApartmentImage.sort_order)).where(
            ApartmentImage.apartment_id == apartment.apartment_id
        )
    ).one()
    next_sort_order = int(max_sort_order or 0) + 1
    now = utc_now()

    apartment_image = ApartmentImage(
        apartment_id=apartment.apartment_id,
        storage_filename=filename,
        original_filename=(file.filename or "image").strip() or "image",
        content_type=(file.content_type or "application/octet-stream").lower(),
        byte_size=len(payload),
        sha256=payload_sha256,
        sort_order=next_sort_order,
        created_at=now,
        updated_at=now,
    )
    session.add(apartment_image)
    session.flush()

    if set_as_guest_background:
        apartment.guest_background_image_id = apartment_image.id
        apartment.guest_background_filename = None
        apartment.guest_background_updated_at = now

    apartment.updated_at = now
    session.add(apartment)
    session.commit()
    session.refresh(apartment_image)
    return apartment_image, True
