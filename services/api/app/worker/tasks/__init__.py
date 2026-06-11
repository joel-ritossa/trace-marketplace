# One module per task. Importing them here registers each on the broker (the
# worker entrypoint imports this package) and keeps call sites on the stable
# `from app.worker.tasks import <task>` path.
from app.worker.tasks.analyze import analyze_trace as analyze_trace
from app.worker.tasks.ingest import ingest_upload as ingest_upload
from app.worker.tasks.ping import ping as ping
from app.worker.tasks.sweep import sweep_stuck_uploads as sweep_stuck_uploads
