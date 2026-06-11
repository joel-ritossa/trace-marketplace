class PermanentIngestError(Exception):
    """Ingestion failure retrying cannot fix (bad payload, not bad infra).

    Raised by importers and the ingest task; the task catches it to mark the
    upload failed immediately with no retry. Anything else is treated as
    transient and retried (6_architecture.md).
    """
