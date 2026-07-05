# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

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
)
def admin_get_apartment_image_file(
    apartment_id: str,
    image_id: int,
    session: Annotated[Session, Depends(get_session)],
    x_admin_token: Annotated[str | None, Header()] = None,
    # TODO(review): Query token is deprecated and remains only for browser media GET requests
    # where setting custom headers is not practical for plain <img> usage.
    admin_token: Annotated[str | None, Query()] = None,
) -> FileResponse:
    if not is_valid_admin_token(x_admin_token or admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")

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
