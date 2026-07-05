# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

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
