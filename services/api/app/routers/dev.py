from fastapi import APIRouter

from app.auth import CurrentUser
from app.schemas.dev import PingEnqueuedResponse, PingResultResponse
from app.worker import broker
from app.worker.tasks import ping

router = APIRouter(prefix="/dev")


@router.post("/ping", response_model=PingEnqueuedResponse)
async def enqueue_ping(user: CurrentUser) -> PingEnqueuedResponse:
    task = await ping.kiq()
    return PingEnqueuedResponse(task_id=task.task_id)


@router.get("/ping/{task_id}", response_model=PingResultResponse)
async def ping_result(task_id: str, user: CurrentUser) -> PingResultResponse:
    backend = broker.result_backend
    if not await backend.is_result_ready(task_id):
        return PingResultResponse(ready=False)
    result = await backend.get_result(task_id)
    if result.is_err:
        return PingResultResponse(ready=True, ok=False, error=str(result.error))
    return PingResultResponse(ready=True, ok=True, result=result.return_value)
