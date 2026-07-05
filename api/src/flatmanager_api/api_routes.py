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
from sqlalchemy import func
from sqlmodel import Session, select

from .db import get_session
from .device_queue import get_queue_manager
from .models import AccessCode, AccessLog, Apartment, ApartmentImage, Device, DoorCommand
from .schemas import (
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
from .security import hash_access_code, hash_device_token
from .settings import settings

router = APIRouter(prefix="/api")
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
    request: Request,
    x_admin_token: Annotated[str | None, Header()] = None,
    admin_token: Annotated[str | None, Query()] = None,
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if client_ip in settings.trusted_ip_set():
        return

    provided_token = x_admin_token or admin_token
    if not provided_token or provided_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


def token_fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:12]


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


@router.get(
    "/admin/apartments",
    response_model=list[AdminApartmentTimezoneSummaryResponse],
    tags=["apartments"],
    summary="List apartments",
    description=(
        "Returns all configured apartments and their timezone metadata. "
        "Optionally filter by apartment_id."
    ),
    dependencies=[Depends(require_admin_token)],
)
def admin_list_apartments(
    session: Annotated[Session, Depends(get_session)],
    apartment_id: str | None = None,
) -> list[AdminApartmentTimezoneSummaryResponse]:
    query = select(Apartment).order_by(Apartment.apartment_id.asc())
    if apartment_id:
        query = query.where(Apartment.apartment_id == apartment_id)

    apartments = session.exec(query).all()
    gallery_counts = count_gallery_images(session, {row.apartment_id for row in apartments})
    return [
        apartment_to_summary(
            apartment,
            gallery_count=gallery_counts.get(apartment.apartment_id, 0),
        )
        for apartment in apartments
    ]


@router.get(
    "/admin/apartments/{apartment_id}",
    response_model=AdminApartmentTimezoneSummaryResponse,
    tags=["apartments"],
    summary="Get apartment",
    description=(
        "Returns one apartment by apartment_id, including timezone and "
        "guest-background availability."
    ),
    dependencies=[Depends(require_admin_token)],
)
def admin_get_apartment(
    apartment_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    gallery_count = count_gallery_images(session, {apartment.apartment_id}).get(
        apartment.apartment_id, 0
    )
    return apartment_to_summary(apartment, gallery_count=gallery_count)


@router.post(
    "/admin/apartments",
    response_model=AdminApartmentTimezoneSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["apartments"],
    summary="Create apartment",
    description=(
        "Creates a new apartment configuration with an IANA timezone used "
        "for schedule and display conversions."
    ),
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
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        postal_code=payload.postal_code,
        city=payload.city,
        country_code=payload.country_code.upper() if payload.country_code else None,
        latitude=payload.latitude,
        longitude=payload.longitude,
        created_at=now,
        updated_at=now,
    )
    session.add(apartment)
    session.commit()
    session.refresh(apartment)

    return apartment_to_summary(apartment, gallery_count=0)


@router.put(
    "/admin/apartments/{apartment_id}/timezone",
    response_model=AdminApartmentTimezoneSummaryResponse,
    tags=["apartments"],
    summary="Update apartment timezone",
    description=(
        "Updates the timezone of an existing apartment. Timezone must be a valid IANA name."
    ),
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

    gallery_count = count_gallery_images(session, {apartment.apartment_id}).get(
        apartment.apartment_id, 0
    )
    return apartment_to_summary(apartment, gallery_count=gallery_count)


@router.patch(
    "/admin/apartments/{apartment_id}",
    response_model=AdminApartmentTimezoneSummaryResponse,
    tags=["apartments"],
    summary="Update apartment metadata",
    description="Updates apartment timezone, address fields, and geo-location metadata.",
    dependencies=[Depends(require_admin_token)],
)
def admin_update_apartment(
    apartment_id: str,
    payload: AdminApartmentUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "timezone" in update_data and update_data["timezone"] is not None:
        update_data["timezone"] = validate_timezone_name(update_data["timezone"])

    if "country_code" in update_data and update_data["country_code"] is not None:
        update_data["country_code"] = update_data["country_code"].upper()

    for field, value in update_data.items():
        setattr(apartment, field, value)

    apartment.updated_at = utc_now()
    session.add(apartment)
    session.commit()
    gallery_count = count_gallery_images(session, {apartment.apartment_id}).get(
        apartment.apartment_id, 0
    )
    return apartment_to_summary(apartment, gallery_count=gallery_count)


@router.post(
    "/admin/apartments/{apartment_id}/guest-background",
    response_model=AdminApartmentTimezoneSummaryResponse,
    tags=["apartments"],
    summary="Upload guest background",
    description=(
        "Uploads or replaces the guest page background image for an apartment (JPG, PNG, WEBP)."
    ),
    dependencies=[Depends(require_admin_token)],
)
async def admin_upload_apartment_guest_background(
    apartment_id: str,
    session: Annotated[Session, Depends(get_session)],
    file: Annotated[UploadFile, File(...)],
) -> AdminApartmentTimezoneSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    await store_apartment_gallery_image(
        session,
        apartment=apartment,
        file=file,
        set_as_guest_background=True,
    )
    refreshed = get_apartment_or_404(session, apartment_id)
    gallery_count = count_gallery_images(session, {apartment_id}).get(apartment_id, 0)
    return apartment_to_summary(refreshed, gallery_count=gallery_count)


@router.delete(
    "/admin/apartments/{apartment_id}/guest-background",
    response_model=AdminApartmentTimezoneSummaryResponse,
    tags=["apartments"],
    summary="Delete guest background",
    description="Removes the apartment-specific guest background image and clears its metadata.",
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_apartment_guest_background(
    apartment_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    existing_path = apartment_background_path(apartment)

    apartment.guest_background_image_id = None
    apartment.guest_background_filename = None
    apartment.guest_background_updated_at = utc_now()
    apartment.updated_at = utc_now()
    session.add(apartment)
    session.commit()

    if existing_path and existing_path.exists():
        existing_path.unlink(missing_ok=True)

    gallery_count = count_gallery_images(session, {apartment_id}).get(apartment_id, 0)
    return apartment_to_summary(apartment, gallery_count=gallery_count)


@router.get(
    "/admin/apartments/{apartment_id}/images",
    response_model=list[ApartmentImageSummaryResponse],
    tags=["apartments"],
    summary="List apartment images",
    description="Returns the apartment image gallery in display order.",
    dependencies=[Depends(require_admin_token)],
)
def admin_list_apartment_images(
    apartment_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> list[ApartmentImageSummaryResponse]:
    apartment = get_apartment_or_404(session, apartment_id)
    images = session.exec(
        select(ApartmentImage)
        .where(ApartmentImage.apartment_id == apartment_id)
        .order_by(ApartmentImage.sort_order.asc(), ApartmentImage.id.asc())
    ).all()
    return [
        apartment_image_to_summary(
            image,
            request=request,
            is_guest_background=(apartment.guest_background_image_id == image.id),
        )
        for image in images
    ]


@router.post(
    "/admin/apartments/{apartment_id}/images",
    response_model=ApartmentImageSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["apartments"],
    summary="Upload apartment image",
    description="Uploads an image into the apartment gallery.",
    dependencies=[Depends(require_admin_token)],
)
async def admin_upload_apartment_image(
    apartment_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    file: Annotated[UploadFile, File(...)],
) -> ApartmentImageSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    image, _created = await store_apartment_gallery_image(
        session,
        apartment=apartment,
        file=file,
        set_as_guest_background=False,
    )
    refreshed = get_apartment_or_404(session, apartment_id)
    return apartment_image_to_summary(
        image,
        request=request,
        is_guest_background=(refreshed.guest_background_image_id == image.id),
    )


@router.post(
    "/admin/apartments/{apartment_id}/images/bulk",
    response_model=ApartmentImageBulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["apartments"],
    summary="Upload multiple apartment images",
    description=(
        "Uploads multiple files into the apartment gallery and ignores duplicates "
        "that already exist for the same apartment."
    ),
    dependencies=[Depends(require_admin_token)],
)
async def admin_upload_apartment_images_bulk(
    apartment_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    files: Annotated[list[UploadFile], File(...)],
) -> ApartmentImageBulkUploadResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided.")

    apartment = get_apartment_or_404(session, apartment_id)
    uploaded_images: list[ApartmentImage] = []
    skipped_images: list[ApartmentImage] = []

    for file in files:
        image, created = await store_apartment_gallery_image(
            session,
            apartment=apartment,
            file=file,
            set_as_guest_background=False,
        )
        if created:
            uploaded_images.append(image)
        else:
            skipped_images.append(image)

    refreshed = get_apartment_or_404(session, apartment_id)
    return ApartmentImageBulkUploadResponse(
        uploaded=[
            apartment_image_to_summary(
                image,
                request=request,
                is_guest_background=(refreshed.guest_background_image_id == image.id),
            )
            for image in uploaded_images
        ],
        skipped_existing=[
            apartment_image_to_summary(
                image,
                request=request,
                is_guest_background=(refreshed.guest_background_image_id == image.id),
            )
            for image in skipped_images
        ],
    )


@router.get(
    "/admin/apartments/{apartment_id}/images/{image_id}/file",
    name="admin_get_apartment_image_file",
    tags=["apartments"],
    summary="Get apartment image file",
    description="Returns the binary file for an apartment gallery image.",
    dependencies=[Depends(require_admin_token)],
)
def admin_get_apartment_image_file(
    apartment_id: str,
    image_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    image = session.get(ApartmentImage, image_id)
    if image is None or image.apartment_id != apartment_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    image_path = apartment_image_path(image)
    if image_path is None or not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    media_type = (
        image.content_type or mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    )
    return FileResponse(image_path, media_type=media_type)


@router.patch(
    "/admin/apartments/{apartment_id}/images/reorder",
    response_model=list[ApartmentImageSummaryResponse],
    tags=["apartments"],
    summary="Reorder apartment images",
    description="Updates sort_order for apartment gallery images.",
    dependencies=[Depends(require_admin_token)],
)
def admin_reorder_apartment_images(
    apartment_id: str,
    payload: ApartmentImageReorderRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> list[ApartmentImageSummaryResponse]:
    apartment = get_apartment_or_404(session, apartment_id)
    existing = session.exec(
        select(ApartmentImage)
        .where(ApartmentImage.apartment_id == apartment_id)
        .order_by(ApartmentImage.id.asc())
    ).all()
    existing_ids = {row.id for row in existing}
    payload_ids = {entry.image_id for entry in payload.items}
    if payload_ids != existing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reorder payload must include all gallery image IDs exactly once.",
        )

    by_id = {row.id: row for row in existing}
    now = utc_now()
    for entry in payload.items:
        image = by_id[entry.image_id]
        image.sort_order = entry.sort_order
        image.updated_at = now
        session.add(image)

    session.commit()

    ordered = session.exec(
        select(ApartmentImage)
        .where(ApartmentImage.apartment_id == apartment_id)
        .order_by(ApartmentImage.sort_order.asc(), ApartmentImage.id.asc())
    ).all()
    return [
        apartment_image_to_summary(
            image,
            request=request,
            is_guest_background=(apartment.guest_background_image_id == image.id),
        )
        for image in ordered
    ]


@router.post(
    "/admin/apartments/{apartment_id}/images/{image_id}/set-guest-background",
    response_model=AdminApartmentTimezoneSummaryResponse,
    tags=["apartments"],
    summary="Set image as guest background",
    description="Marks a gallery image as the active guest background for the apartment.",
    dependencies=[Depends(require_admin_token)],
)
def admin_set_guest_background_image(
    apartment_id: str,
    image_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> AdminApartmentTimezoneSummaryResponse:
    apartment = get_apartment_or_404(session, apartment_id)
    image = session.get(ApartmentImage, image_id)
    if image is None or image.apartment_id != apartment_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    apartment.guest_background_image_id = image.id
    apartment.guest_background_filename = None
    apartment.guest_background_updated_at = utc_now()
    apartment.updated_at = utc_now()
    session.add(apartment)
    session.commit()
    gallery_count = count_gallery_images(session, {apartment_id}).get(apartment_id, 0)
    return apartment_to_summary(apartment, gallery_count=gallery_count)


@router.delete(
    "/admin/apartments/{apartment_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["apartments"],
    summary="Delete apartment image",
    description="Deletes one gallery image and clears guest background mapping when applicable.",
    dependencies=[Depends(require_admin_token)],
)
def admin_delete_apartment_image(
    apartment_id: str,
    image_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    apartment = get_apartment_or_404(session, apartment_id)
    image = session.get(ApartmentImage, image_id)
    if image is None or image.apartment_id != apartment_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    if apartment.guest_background_image_id == image.id:
        apartment.guest_background_image_id = None
        apartment.guest_background_updated_at = utc_now()
        apartment.updated_at = utc_now()
        session.add(apartment)

    image_path = apartment_image_path(image)
    session.delete(image)
    session.commit()

    if image_path and image_path.exists():
        image_path.unlink(missing_ok=True)


@router.delete(
    "/admin/apartments/{apartment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["apartments"],
    summary="Delete apartment",
    description="Deletes an apartment when it has no dependent devices or access codes.",
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

    has_images = session.exec(
        select(ApartmentImage.id).where(ApartmentImage.apartment_id == apartment_id).limit(1)
    ).first()
    if has_images is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete apartment with existing gallery images.",
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


@router.post(
    "/guest/open",
    response_model=GuestOpenResponse,
    tags=["guest"],
    summary="Request guest door open",
    description=(
        "Validates apartment and access code constraints, logs the attempt, "
        "and queues an open command if accepted."
    ),
)
def guest_open(
    payload: GuestOpenRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> GuestOpenResponse:
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    trusted_ip = ip_address in settings.trusted_ip_set()

    if not trusted_ip and is_rate_limited(
        session, apartment_id=payload.apartment_id, ip_address=ip_address
    ):
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result="rate_limited",
            reason="rate_limit",
        )
        session.commit()
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE).model_dump(),
        )

    if not trusted_ip and is_locked_out(
        session, apartment_id=payload.apartment_id, ip_address=ip_address
    ):
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result="denied",
            reason="lockout",
        )
        session.commit()
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE).model_dump(),
        )

    if not trusted_ip and is_retry_too_fast(
        session, apartment_id=payload.apartment_id, ip_address=ip_address
    ):
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            result="rate_limited",
            reason="retry_too_fast",
        )
        session.commit()
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE).model_dump(),
        )

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

    # Signal device queue that a command is ready
    get_queue_manager().notify(device.id)

    return GuestOpenResponse(status="accepted", message=SUCCESS_MESSAGE, command_id=command.id)


@router.get(
    "/guest/background-url",
    response_model=GuestBackgroundUrlResponse,
    tags=["guest"],
    summary="Get signed guest background URL",
    description=(
        "Returns a short-lived signed URL for the apartment guest background "
        "image, or null when none exists."
    ),
)
def guest_background_url(
    apartment_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> GuestBackgroundUrlResponse:
    apartment = session.exec(
        select(Apartment).where(Apartment.apartment_id == apartment_id)
    ).first()
    if apartment is None:
        return GuestBackgroundUrlResponse(image_url=None)

    has_background = apartment.guest_background_image_id is not None
    if not has_background and apartment.guest_background_filename is None:
        return GuestBackgroundUrlResponse(image_url=None)

    return GuestBackgroundUrlResponse(image_url=build_guest_background_url(request, apartment_id))


@router.get(
    "/guest/background/{apartment_id}",
    name="guest_get_background",
    tags=["guest"],
    summary="Download guest background",
    description=(
        "Serves the guest background image for an apartment when signature and "
        "expiry parameters are valid."
    ),
)
def guest_get_background(
    apartment_id: str,
    exp: int,
    sig: str,
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    if exp < int(time.time()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not verify_guest_background_signature(apartment_id, exp, sig):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    apartment = session.exec(
        select(Apartment).where(Apartment.apartment_id == apartment_id)
    ).first()
    if apartment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if apartment.guest_background_image_id is not None:
        apartment_image = session.get(ApartmentImage, apartment.guest_background_image_id)
        if apartment_image is None or apartment_image.apartment_id != apartment_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        image_path = apartment_image_path(apartment_image)
        if image_path is None or not image_path.exists() or not image_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

        media_type = apartment_image.content_type or mimetypes.guess_type(image_path.name)[0]
        return FileResponse(
            image_path,
            media_type=media_type or "application/octet-stream",
            headers={"Cache-Control": "private, max-age=60"},
        )

    background_path = apartment_background_path(apartment)
    if background_path is None or not background_path.exists() or not background_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    media_type = mimetypes.guess_type(background_path.name)[0] or "application/octet-stream"
    return FileResponse(
        background_path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get(
    "/guest/command-status/{command_id}",
    response_model=GuestCommandStatusResponse,
    tags=["guest"],
    summary="Get guest command status",
    description="Returns the current status of a guest-issued door command for the same apartment.",
)
def guest_command_status(
    command_id: int,
    apartment_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> GuestCommandStatusResponse:
    command = session.exec(
        select(DoorCommand).where(
            DoorCommand.id == command_id,
            DoorCommand.apartment_id == apartment_id,
            DoorCommand.source == "guest",
        )
    ).first()

    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")

    return GuestCommandStatusResponse(status=command.status)


@router.get(
    "/device/wait-command",
    response_model=WaitCommandResponse,
    tags=["device_agent"],
    summary="Device long-poll for command",
    description=(
        "Authenticated device endpoint that waits for pending commands and "
        "atomically claims one when available."
    ),
)
async def wait_command(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    device: Annotated[Device, Depends(get_current_device)],
) -> WaitCommandResponse:
    """
    Blocking queue wait-command endpoint.

    1. Update heartbeat on entry
    2. Check for pending non-expired command
    3. If found, atomically claim and return
    4. If not found, wait for queue signal or timeout
    5. After signal, fetch again and claim atomically
    6. Update heartbeat on exit
    """
    now = utc_now()

    # Heartbeat: entry
    device.last_seen = now
    device.updated_at = now
    device.last_ip = request.client.host if request.client else None
    device.online_status = "online"
    session.add(device)
    session.commit()

    try:
        # Lazy-expire stale pending commands
        expire_pending_commands(session, device_id=device.id)

        # Initial fetch: oldest non-expired pending command
        command = fetch_oldest_pending_command(session, device_id=device.id)

        if command is not None:
            # Atomically claim
            claimed = try_claim_command(session, command_id=command.id, device_id=device.id)
            if claimed:
                return WaitCommandResponse(
                    command_id=claimed.id,
                    command=claimed.command,
                    duration_ms=claimed.duration_ms,
                    expires_at=claimed.expires_at,
                )

        # No command available; wait for queue signal or timeout
        queue_manager = get_queue_manager()
        signaled = await queue_manager.wait_for_signal(
            device.id, timeout_seconds=settings.long_poll_timeout_seconds
        )

        if signaled:
            # Signal received; fetch again and attempt claim
            command = fetch_oldest_pending_command(session, device_id=device.id)
            if command is not None:
                claimed = try_claim_command(session, command_id=command.id, device_id=device.id)
                if claimed:
                    return WaitCommandResponse(
                        command_id=claimed.id,
                        command=claimed.command,
                        duration_ms=claimed.duration_ms,
                        expires_at=claimed.expires_at,
                    )

        # Timeout or no command after signal
        return WaitCommandResponse(command="none")

    except asyncio.CancelledError:
        # Uvicorn may cancel long-poll requests during shutdown once graceful timeout elapses.
        logger.info("wait-command cancelled during shutdown for device_id=%s", device.id)
        return WaitCommandResponse(command="none")

    finally:
        # Heartbeat: exit
        now = utc_now()
        device.last_seen = now
        device.updated_at = now
        session.add(device)
        session.commit()


@router.post(
    "/device/command-result",
    response_model=CommandResultResponse,
    tags=["device_agent"],
    summary="Submit command execution result",
    description=(
        "Authenticated device endpoint to acknowledge a command and report execution outcome."
    ),
)
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


@router.get(
    "/admin/commands/recent",
    response_model=list[CommandSummaryResponse],
    tags=["commands"],
    summary="List recent commands",
    description=(
        "Returns recently created door commands with optional apartment filter "
        "and bounded result limit."
    ),
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
    tags=["access_logs"],
    summary="List recent access logs",
    description=(
        "Returns recent access events for auditing, with optional apartment "
        "filter and bounded result limit."
    ),
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
    tags=["commands"],
    summary="Delete all commands",
    description=(
        "Deletes all stored door commands. Intended for maintenance and test reset workflows."
    ),
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
    tags=["access_logs"],
    summary="Delete all access logs",
    description=(
        "Deletes all access log entries. Intended for maintenance and test reset workflows."
    ),
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
    tags=["commands"],
    summary="Request manual open",
    description=(
        "Creates an admin-triggered open command for an apartment and notifies "
        "the assigned device queue."
    ),
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

    # Signal device queue that a command is ready
    get_queue_manager().notify(device.id)

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
    tags=["access_codes"],
    summary="List access codes",
    description=(
        "Returns configured access codes with validity windows, use counters, and active status."
    ),
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
    tags=["access_codes"],
    summary="Create access code",
    description=(
        "Creates an apartment access code with validity window and usage "
        "limits. Code must be numeric (digits only)."
    ),
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
    valid_from = normalize_datetime_to_utc(payload.valid_from, input_timezone=input_timezone)
    valid_until = normalize_datetime_to_utc(payload.valid_until, input_timezone=input_timezone)

    if has_overlapping_code_window(
        session,
        apartment_id=payload.apartment_id,
        code_hash=code_hash,
        valid_from=valid_from,
        valid_until=valid_until,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Code already exists in an overlapping time window for this apartment. "
                "Please choose a different code."
            ),
        )

    access_code = AccessCode(
        apartment_id=payload.apartment_id,
        code_hash=code_hash,
        valid_from=valid_from,
        valid_until=valid_until,
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
    tags=["access_codes"],
    summary="Update access code",
    description=(
        "Updates mutable access code fields such as validity window, max uses, "
        "metadata, or active flag."
    ),
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
    tags=["access_codes"],
    summary="Deactivate access code",
    description="Marks an access code as inactive so it can no longer be used by guests.",
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
    tags=["access_codes"],
    summary="Delete access code",
    description="Permanently deletes an access code record.",
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
