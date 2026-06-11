"""Redis token-bucket rate limiting (6_architecture.md).

Four buckets: global, per-user, and global + per-user buckets on uploads.
State lives in Redis so limits hold across API instances. The per-user key is
the JWT sub claim parsed *without* verification — auth happens in the route
dependency; here we only need a cheap stable key (a forged sub only rate-limits
the forger). Unauthenticated requests are covered by the global bucket alone.
"""

import hashlib
import logging
import time

import jwt
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.auth import API_KEY_PREFIX
from app.clients import redis
from app.config import settings
from app.errors import error_response

logger = logging.getLogger(__name__)

# Atomic refill-and-take. Returns {allowed, retry_after_seconds}.
_TOKEN_BUCKET_LUA = """
local tokens_key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', tokens_key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil then
  tokens = burst
  ts = now
end
tokens = math.min(burst, tokens + (now - ts) * rate)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_after = math.ceil((1 - tokens) / rate)
end

redis.call('HSET', tokens_key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', tokens_key, math.ceil(burst / rate) + 60)
return {allowed, retry_after}
"""

_EXEMPT_PATHS = {"/v1/health"}


def _subject(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:]
    # API keys bucket on the token's digest — same cheap-stable-key rationale
    # as the unverified sub below (a forged key only rate-limits the forger),
    # and no DB lookup in the middleware.
    if token.startswith(API_KEY_PREFIX):
        return "key:" + hashlib.sha256(token.encode()).hexdigest()[:32]
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return None
    return claims.get("sub")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._script = None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        is_upload = request.method == "POST" and request.url.path == "/v1/uploads"
        buckets: list[tuple[str, float, int]] = [
            ("rl:global", settings.rate_limit_global_rate, settings.rate_limit_global_burst),
        ]
        if is_upload:
            buckets.append(
                (
                    "rl:upload:global",
                    settings.rate_limit_upload_global_per_minute / 60.0,
                    settings.rate_limit_upload_global_per_minute,
                )
            )
        sub = _subject(request)
        if sub:
            buckets.append(
                (f"rl:user:{sub}", settings.rate_limit_user_rate, settings.rate_limit_user_burst)
            )
            if is_upload:
                buckets.append(
                    (
                        f"rl:upload:{sub}",
                        settings.rate_limit_upload_per_minute / 60.0,
                        settings.rate_limit_upload_per_minute,
                    )
                )

        # Fail open on Redis loss: rate-limit state is not state of record, so
        # the limiter's backing store must not gate Postgres-only reads.
        try:
            if self._script is None:
                self._script = redis.client().register_script(_TOKEN_BUCKET_LUA)
            now = time.time()
            for key, rate, burst in buckets:
                allowed, retry_after = await self._script(keys=[key], args=[rate, burst, now])
                if not allowed:
                    return error_response(
                        "rate_limited",
                        "Too many requests; slow down.",
                        429,
                        headers={"Retry-After": str(max(1, int(retry_after)))},
                    )
        except (RedisError, OSError) as exc:
            logger.warning("rate limiter unavailable (%s); failing open", exc)

        return await call_next(request)
