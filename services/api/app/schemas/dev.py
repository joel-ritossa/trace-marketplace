from pydantic import BaseModel


class PingEnqueuedResponse(BaseModel):
    task_id: str


class PingResultResponse(BaseModel):
    ready: bool
    ok: bool | None = None
    result: dict | None = None
    error: str | None = None
