# ruff: noqa: F403,F405
from fastapi import APIRouter

from .deps import *

router = APIRouter(prefix="/api")

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
