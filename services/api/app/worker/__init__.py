# Importing tasks registers them on the broker. This module exists for the
# taskiq CLI entrypoint (`taskiq worker app.worker:broker`); application code
# should import from app.worker.broker / app.worker.tasks directly.
from app.worker import tasks as tasks
from app.worker.broker import broker as broker
