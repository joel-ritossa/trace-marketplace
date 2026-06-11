from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.errors import ApiError

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None


@lru_cache(maxsize=1)
def _jwk_client() -> jwt.PyJWKClient:
    # Supabase signs access tokens with an asymmetric key (ES256); keys are
    # published at the JWKS endpoint. cache_keys avoids re-parsing the JWK on
    # every request (the JWKS fetch itself is cached by lifespan).
    return jwt.PyJWKClient(settings.supabase_jwks_url, cache_keys=True)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    if credentials is None:
        raise ApiError("unauthorized", "Missing bearer token.", status=401)
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"require": ["sub", "exp"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError):
        raise ApiError("unauthorized", "Invalid token.", status=401) from None
    return AuthUser(id=claims["sub"], email=claims.get("email"))


CurrentUser = Annotated[AuthUser, Depends(current_user)]
