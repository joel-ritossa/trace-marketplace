import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clients import db
from app.config import settings
from app.errors import ApiError
from app.queries import allowed_emails, api_keys

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

API_KEY_PREFIX = "tmk_"


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None
    via: Literal["jwt", "api_key"] = "jwt"


@lru_cache(maxsize=1)
def _jwk_client() -> jwt.PyJWKClient:
    # Supabase signs access tokens with an asymmetric key (ES256); keys are
    # published at the JWKS endpoint. cache_keys avoids re-parsing the JWK on
    # every request (the JWKS fetch itself is cached by lifespan).
    return jwt.PyJWKClient(settings.supabase_jwks_url, cache_keys=True)


async def _jwt_user(token: str) -> AuthUser:
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError):
        raise ApiError("unauthorized", "Invalid token.", status=401) from None
    email = claims.get("email")
    # Allowlist guard: signup is blocked by a DB trigger on auth.users; this
    # per-request check is what locks out existing sessions and sign-ins for
    # emails later removed from allowed_emails. Fail closed on missing email.
    if not email or not await allowed_emails.is_allowed(db.pool(), email):
        raise ApiError("email_not_allowed", "This email is not on the allowlist.", status=403)
    return AuthUser(id=claims["sub"], email=email)


async def _api_key_user(token: str) -> AuthUser:
    # Deliberately no allowlist re-check (A1 audit): minting required an
    # allowlisted JWT, and key offboarding is revocation — removing an email
    # from allowed_emails kills sessions but not previously minted keys.
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    row = await api_keys.find_active_by_hash(db.pool(), key_hash)
    if row is None:
        raise ApiError("unauthorized", "Invalid API key.", status=401)
    # Bookkeeping must never fail auth; the query itself throttles writes.
    try:
        await api_keys.touch_last_used(db.pool(), str(row["id"]))
    except Exception:
        logger.warning("api key %s: last_used_at update failed", row["id"], exc_info=True)
    return AuthUser(id=str(row["owner_id"]), email=None, via="api_key")


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    """JWT-only principal — every endpoint except the upload pair (3_api.md:
    API-key principals reach exactly POST /v1/uploads and GET /v1/uploads/{id})."""
    if credentials is None:
        raise ApiError("unauthorized", "Missing bearer token.", status=401)
    if credentials.credentials.startswith(API_KEY_PREFIX):
        raise ApiError("unauthorized", "API keys are only valid for upload endpoints.", status=401)
    return await _jwt_user(credentials.credentials)


async def upload_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    """Dual principal for the upload pair: Supabase JWT or `tmk_` API key on
    the same Authorization header (the one stage-1 auth change)."""
    if credentials is None:
        raise ApiError("unauthorized", "Missing bearer token.", status=401)
    if credentials.credentials.startswith(API_KEY_PREFIX):
        return await _api_key_user(credentials.credentials)
    return await _jwt_user(credentials.credentials)


CurrentUser = Annotated[AuthUser, Depends(current_user)]
UploadPrincipal = Annotated[AuthUser, Depends(upload_principal)]
