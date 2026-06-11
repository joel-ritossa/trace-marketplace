"""Notification view models (3_api.md Notifications).

Mirrored by the frontend types in apps/web/src/lib/api/notifications.ts.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator

# type is app-validated text (review_request | subscription_match |
# upload_failed today); new types are additive, so the schema keeps str.


class NotificationItem(BaseModel):
    notification_id: str
    type: str
    # Type-specific, always enough to build the link target (2_data-model.md).
    payload: dict[str, Any]
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItem]
    total: int
    unread_count: int


class NotificationsReadRequest(BaseModel):
    """Body is `{"ids": [...]}` or `{"all": true}` — exactly one (3_api.md)."""

    ids: list[str] | None = None
    all: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> "NotificationsReadRequest":
        if self.all == (self.ids is not None):
            raise ValueError("Provide either ids or all: true, not both.")
        return self
