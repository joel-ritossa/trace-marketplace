from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# Mirrors the uploads.status check constraint and the frontend UploadStatus
# union (apps/web/src/lib/api/uploads.ts).
UploadStatus = Literal["received", "processing", "complete", "failed"]


class UploadCreatedResponse(BaseModel):
    upload_id: str
    status: UploadStatus
    sha256: str


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    status: UploadStatus
    error_message: str | None
    parse_warnings: dict[str, Any] | None
    trace_ids: list[str]
    created_at: datetime
    processed_at: datetime | None


class UploadListItem(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    status: UploadStatus
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None


class UploadListResponse(BaseModel):
    uploads: list[UploadListItem]
    total: int
