# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

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
