import asyncpg
from fastapi import APIRouter, Query, Response

from app.auth import CurrentUser
from app.clients import db
from app.queries import notifications as notifications_q
from app.schemas.notification import (
    NotificationItem,
    NotificationListResponse,
    NotificationsReadRequest,
)

router = APIRouter(prefix="/notifications")


def _item(row: asyncpg.Record) -> NotificationItem:
    return NotificationItem(
        notification_id=str(row["id"]),
        type=row["type"],
        payload=row["payload"],
        created_at=row["created_at"],
        read_at=row["read_at"],
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NotificationListResponse:
    rows, total, unread = await notifications_q.list_for_user(
        db.pool(), user.id, limit=limit, offset=offset
    )
    return NotificationListResponse(
        notifications=[_item(r) for r in rows], total=total, unread_count=unread
    )


@router.post("/read", status_code=204)
async def mark_read(body: NotificationsReadRequest, user: CurrentUser) -> Response:
    """Idempotent (3_api.md): already-read, foreign, and malformed ids no-op
    alike — none of them are the caller's unread notifications."""
    try:
        await notifications_q.mark_read(db.pool(), user.id, ids=body.ids, mark_all=body.all)
    except asyncpg.DataError:  # not a UUID
        pass
    return Response(status_code=204)
