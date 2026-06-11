from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# Mirrors the uploads.status check constraint and the frontend UploadStatus
# union (apps/web/src/lib/api/uploads.ts).
UploadStatus = Literal["received", "processing", "complete", "failed"]

# Mirrors the uploads.source check constraint; set by the API from auth type.
UploadSource = Literal["cli", "web"]


class UploadCreatedResponse(BaseModel):
    upload_id: str
    status: UploadStatus
    sha256: str


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    status: UploadStatus
    source: UploadSource
    error_message: str | None
    parse_warnings: dict[str, Any] | None
    # Per-kind replacement counts from the last ingestion (7_redaction.md);
    # null when nothing was masked or the upload hasn't completed.
    redaction_counts: dict[str, int] | None
    trace_ids: list[str]
    created_at: datetime
    processed_at: datetime | None


class UploadListItem(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    status: UploadStatus
    source: UploadSource
    error_message: str | None
    redaction_counts: dict[str, int] | None
    trace_ids: list[str]
    created_at: datetime
    processed_at: datetime | None


class UploadListResponse(BaseModel):
    uploads: list[UploadListItem]
    total: int
