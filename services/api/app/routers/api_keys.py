import hashlib
import secrets
import string

import asyncpg
from fastapi import APIRouter

from app.auth import API_KEY_PREFIX, CurrentUser
from app.clients import db
from app.errors import ApiError
from app.queries import api_keys
from app.schemas.api_key import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyListItem,
    ApiKeyListResponse,
)

router = APIRouter(prefix="/api-keys")

_KEY_ALPHABET = string.ascii_lowercase + string.digits
_KEY_RANDOM_CHARS = 32


def _mint_key() -> tuple[str, str, str]:
    """Returns (plaintext, sha256 hash, display form). Format per 3_api.md:
    tmk_ + 32 random chars; display = prefix+2 … last 4 (tmk_ab…f3k9)."""
    plaintext = API_KEY_PREFIX + "".join(
        secrets.choice(_KEY_ALPHABET) for _ in range(_KEY_RANDOM_CHARS)
    )
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    key_display = f"{plaintext[:6]}…{plaintext[-4:]}"
    return plaintext, key_hash, key_display


@router.post("", status_code=201, response_model=ApiKeyCreatedResponse)
async def create_api_key(body: ApiKeyCreateRequest, user: CurrentUser) -> ApiKeyCreatedResponse:
    plaintext, key_hash, key_display = _mint_key()
    row = await api_keys.create(
        db.pool(),
        owner_id=user.id,
        name=body.name,
        key_hash=key_hash,
        key_display=key_display,
    )
    return ApiKeyCreatedResponse(
        api_key=plaintext,
        api_key_id=str(row["id"]),
        name=row["name"],
        key_display=row["key_display"],
        scope=row["scope"],
        created_at=row["created_at"],
    )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(user: CurrentUser) -> ApiKeyListResponse:
    rows = await api_keys.list_owned(db.pool(), user.id)
    return ApiKeyListResponse(
        api_keys=[
            ApiKeyListItem(
                api_key_id=str(r["id"]),
                name=r["name"],
                key_display=r["key_display"],
                scope=r["scope"],
                created_at=r["created_at"],
                last_used_at=r["last_used_at"],
                revoked_at=r["revoked_at"],
            )
            for r in rows
        ]
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, user: CurrentUser) -> None:
    try:
        revoked = await api_keys.revoke(db.pool(), key_id, user.id)
    except asyncpg.DataError:  # not a UUID
        revoked = False
    if not revoked:
        # 404 (not 403) so callers can't probe for other users' keys.
        raise ApiError("not_found", "API key not found.", status=404)
