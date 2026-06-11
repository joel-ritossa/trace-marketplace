"""Entrypoint for the scheduler service: `taskiq scheduler app.worker.scheduler:scheduler`.

Fires tasks declared with schedule labels (the stuck-upload sweep). The
scheduler only enqueues — execution happens in the worker — so it opens no
DB/storage clients of its own.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.worker import tasks as tasks  # registers tasks on the broker
from app.worker.broker import broker

scheduler = TaskiqScheduler(broker, sources=[LabelScheduleSource(broker)])
