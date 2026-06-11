# Importing tasks registers them on the broker — required for both the worker
# process (so it can execute them) and the API (so it can enqueue them).
from app.worker import tasks as tasks
from app.worker.broker import broker as broker
