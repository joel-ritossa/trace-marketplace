"""Dev-only fault injection for demoing the retry/DLQ paths.

POST /v1/uploads accepts an X-Fault header (honored only when dev_routes is
on); the spec is stashed in Redis and the ingest task trips on it:

- ``transient:N`` — fail the first N attempts, then succeed (retry demo).
- ``exhaust``     — fail every attempt (dead-letter demo).
- ``permanent``   — raise PermanentIngestError (immediate-fail demo).
"""

import re

from app.clients import redis
from app.config import settings
from app.importers.errors import PermanentIngestError

_SPEC_RE = re.compile(r"^(permanent|exhaust|transient:\d+)$")
_TTL_SECONDS = 3600


def is_valid(spec: str) -> bool:
    return _SPEC_RE.match(spec) is not None


async def arm(upload_id: str, spec: str) -> None:
    await redis.client().set(f"fault:{upload_id}", spec, ex=_TTL_SECONDS)


async def trip(upload_id: str, attempt: int) -> None:
    """Raise the armed fault for this upload, if any. No-op outside dev."""
    if not settings.dev_routes:
        return
    raw = await redis.client().get(f"fault:{upload_id}")
    if raw is None:
        return
    spec = raw.decode()
    if spec == "permanent":
        raise PermanentIngestError("Fault injection: permanent failure.")
    if spec == "exhaust":
        raise RuntimeError("Fault injection: transient failure (exhaust).")
    failures = int(spec.split(":", 1)[1])
    if attempt <= failures:
        raise RuntimeError(f"Fault injection: transient failure (attempt {attempt}/{failures}).")
