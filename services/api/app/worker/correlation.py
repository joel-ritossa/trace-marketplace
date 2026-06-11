"""Carries correlation ids from enqueue site to worker execution (app/obs.py).

On send, the current correlation id (the HTTP request's, or the enqueuing
task's) is stamped onto the message as a label — setdefault, so the retry
re-kick (which copies labels) and any pre-labeled message keep their id. On
execute, the label becomes the worker-side contextvar and the task name is
bound, so every log line in the task carries both without per-task plumbing.

Each message executes in its own asyncio task (own contextvar copy), so
nothing here leaks across concurrent task runs.
"""

from taskiq import TaskiqMiddleware
from taskiq.message import TaskiqMessage

from app import obs


class CorrelationMiddleware(TaskiqMiddleware):
    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        message.labels.setdefault(
            "correlation_id", obs.get_correlation_id() or obs.new_correlation_id()
        )
        return message

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        cid = message.labels.get("correlation_id") or obs.new_correlation_id()
        obs.correlation_id_var.set(cid)
        obs.bind(task=message.task_name)
        return message
