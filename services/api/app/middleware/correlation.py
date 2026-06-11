"""Per-request correlation ids (app/obs.py).

Honors a caller-supplied X-Correlation-ID (sanitized — it lands in logs) or
mints one, sets the contextvar for the request's duration so every log line
and task enqueue inherits it, and echoes it on the response so a client can
quote the id when reporting a problem.
"""

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app import obs

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-correlation-id")
        cid = supplied if supplied and _SAFE_ID.match(supplied) else obs.new_correlation_id()
        token = obs.correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            obs.correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = cid
        return response
