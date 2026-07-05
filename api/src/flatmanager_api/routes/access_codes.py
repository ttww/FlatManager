# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

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
