# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

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

    update_result = session.exec(
        update(AccessCode)
        .where(AccessCode.id == access_code.id)
        .where(AccessCode.used_count < AccessCode.max_uses)
        .values(used_count=AccessCode.used_count + 1, updated_at=now)
    )
    if update_result.rowcount != 1:
        log_access_event(
            session,
            apartment_id=payload.apartment_id,
            ip_address=ip_address,
            user_agent=user_agent,
            access_code_id=access_code.id,
            result="denied",
            reason="validation_failed",
        )
        session.commit()
        return GuestOpenResponse(status="denied", message=NEUTRAL_DENIED_MESSAGE)

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
