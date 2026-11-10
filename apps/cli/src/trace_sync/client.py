"""Upload + status-poll calls against the upload API (5_cli.md).

429s honor Retry-After and retry indefinitely: provider backpressure is
normal operation, not failure. Everything else maps to a per-file outcome —
one bad file never stops the run.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import zstandard

from trace_sync.files import sibling_transcripts, upload_bytes, upload_name

POLL_TIMEOUT_SECONDS = 120.0
RETRY_AFTER_CAP_SECONDS = 60.0
_PREFLIGHT_PROBE_ID = "00000000-0000-0000-0000-000000000000"


class FatalError(Exception):
    """The run cannot proceed at all (bad key, unreachable API) — exit 2."""


@dataclass(frozen=True)
class FileOutcome:
    kind: str  # uploaded | skipped | failed
    detail: str  # human line suffix, e.g. "complete, 3 traces"
    # Transport-level failure (network error, unreadable file): the server
    # never rejected the bytes, so watch mode may offer the file again.
    # Server rejections and ingestion failures stay non-retryable — a
    # permanently bad file must not loop.
    retryable: bool = False


@dataclass
class PendingUpload:
    """An accepted upload whose ingestion hasn't reached a terminal state."""

    path: Path
    upload_id: str
    deadline: float  # time.monotonic() cutoff for status polling
    note: str = ""  # appended to the outcome line


class SyncClient:
    def __init__(self, api_url: str, api_key: str) -> None:
        self._http = httpx.Client(
            base_url=api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._http.close()

    def preflight(self) -> None:
        """Fail fast on a bad key or unreachable API before touching files.

        Probes GET /v1/uploads/{nil-uuid}: 404 proves the key authenticates
        (the upload pair is the key's whole surface), 401 means it doesn't.
        """
        try:
            res = self._request("GET", f"/v1/uploads/{_PREFLIGHT_PROBE_ID}")
        except httpx.HTTPError as exc:
            raise FatalError(f"cannot reach API: {exc}") from None
        if res.status_code == 401:
            raise FatalError(f"API key rejected: {_error_message(res)}")

    def enqueue(self, path: Path) -> FileOutcome | PendingUpload:
        """POST the file; ingestion runs server-side off the queue, so this
        returns as soon as the upload is accepted (5_cli.md: pipelined).
        A session the server rejects as too large retries once without the
        subagent transcripts borrowed from sibling sessions."""
        try:
            res = self._post(path, siblings=True)
            note = ""
            if res.status_code == 413 and (borrowed := sibling_transcripts(path)):
                res = self._post(path, siblings=False)
                plural = "" if borrowed == 1 else "s"
                note = (
                    f"; {borrowed} subagent transcript{plural} from earlier sessions"
                    " left out — over the size limit"
                )
        except OSError as exc:
            return FileOutcome("failed", f"failed: {exc}", retryable=True)
        except zstandard.ZstdError as exc:
            return FileOutcome("failed", f"failed: cannot decompress {path.name}: {exc}")
        except httpx.HTTPError as exc:
            return FileOutcome("failed", f"failed: {exc}", retryable=True)

        if res.status_code == 201:
            deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
            return PendingUpload(path, res.json()["upload_id"], deadline, note)
        if res.status_code == 409 and _error_code(res) == "duplicate_upload":
            return FileOutcome("skipped", f"already synced{note}")
        return FileOutcome("failed", f"failed: {_error_message(res)}")

    def _post(self, path: Path, siblings: bool) -> httpx.Response:
        data = upload_bytes(path, siblings)
        file = (upload_name(path), data, "application/json")
        return self._request("POST", "/v1/uploads", files={"file": file})

    def check(self, pending: PendingUpload) -> FileOutcome | None:
        """One status poll: a terminal outcome, or None while still ingesting."""
        if time.monotonic() >= pending.deadline:
            return FileOutcome(
                "failed",
                f"failed: ingestion not finished after {POLL_TIMEOUT_SECONDS:.0f}s "
                f"(check /uploads for upload {pending.upload_id})",
            )
        try:
            res = self._request("GET", f"/v1/uploads/{pending.upload_id}")
        except httpx.HTTPError as exc:
            # The upload itself landed; a retry dedupes to "already
            # synced" rather than leaving the file silently dropped.
            return FileOutcome("failed", f"failed: status poll error: {exc}", retryable=True)
        if res.status_code != 200:
            return FileOutcome("failed", f"failed: status poll: {_error_message(res)}")
        body = res.json()
        if body["status"] == "complete":
            count = len(body["trace_ids"])
            plural = "" if count == 1 else "s"
            return FileOutcome(
                "uploaded", f"uploaded (complete, {count} trace{plural}{pending.note})"
            )
        if body["status"] == "failed":
            return FileOutcome("failed", f"failed: {body['error_message']}")
        return None

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """One request, sleeping out 429s (Retry-After honored, capped)."""
        while True:
            res = self._http.request(method, path, **kwargs)
            if res.status_code != 429:
                return res
            try:
                wait = float(res.headers.get("retry-after", "5"))
            except ValueError:
                wait = 5.0
            time.sleep(min(max(wait, 1.0), RETRY_AFTER_CAP_SECONDS))


def _error_code(res: httpx.Response) -> str:
    try:
        return res.json()["error"]["code"]
    except Exception:
        return "unknown"


def _error_message(res: httpx.Response) -> str:
    try:
        return res.json()["error"]["message"]
    except Exception:
        return f"HTTP {res.status_code}"
