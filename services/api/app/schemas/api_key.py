from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

KeyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ApiKeyCreateRequest(BaseModel):
    name: KeyName


class ApiKeyListItem(BaseModel):
    api_key_id: str
    name: str
    key_display: str
    scope: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreatedResponse(BaseModel):
    # The only response that ever carries the plaintext key (3_api.md:
    # "plaintext exactly once").
    api_key: str
    api_key_id: str
    name: str
    key_display: str
    scope: str
    created_at: datetime


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyListItem]
