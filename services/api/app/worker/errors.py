class PermanentIngestError(Exception):
    """Ingestion failure retrying cannot fix (bad payload, not bad infra).

    Tasks raise this to mark the upload failed immediately with no retry;
    anything else is treated as transient and retried (6_architecture.md).
    """
