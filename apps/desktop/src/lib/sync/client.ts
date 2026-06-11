import { readFile } from "@tauri-apps/plugin-fs";
import { apiRequest } from "../api";

// Upload + status-poll calls against the upload API — a TS port of
// apps/cli/src/trace_sync/client.py, same semantics. Keep in sync.
// 429s honor Retry-After and retry indefinitely: provider backpressure is
// normal operation, not failure. Everything else maps to a per-file outcome —
// one bad file never stops the run.

const POLL_TIMEOUT_MS = 120_000;
const RETRY_AFTER_CAP_MS = 60_000;

export type OutcomeKind = "uploaded" | "skipped" | "failed";

export type FileOutcome = {
  kind: OutcomeKind;
  detail: string; // human line suffix, e.g. "uploaded (complete, 3 traces)"
  // Transport-level failure (network error, unreadable file): the server
  // never rejected the bytes, so watch mode may offer the file again.
  // Server rejections and ingestion failures stay non-retryable — a
  // permanently bad file must not loop.
  retryable: boolean;
};

export type PendingUpload = {
  path: string;
  uploadId: string;
  deadline: number; // Date.now() cutoff for status polling
};

function basename(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** One request, sleeping out 429s (Retry-After honored, capped). */
async function request(path: string, init?: RequestInit): Promise<Response> {
  for (;;) {
    const res = await apiRequest(path, init);
    if (res.status !== 429) return res;
    const parsed = Number.parseFloat(res.headers.get("retry-after") ?? "5");
    const waitS = Number.isNaN(parsed) ? 5 : parsed;
    await sleep(Math.min(Math.max(waitS * 1000, 1000), RETRY_AFTER_CAP_MS));
  }
}

async function errorBody(res: Response): Promise<{ code: string; message: string }> {
  try {
    const body = await res.json();
    return { code: body.error.code, message: body.error.message };
  } catch {
    return { code: "unknown", message: `HTTP ${res.status}` };
  }
}

/** POST the file; ingestion runs server-side off the queue, so this returns
 *  as soon as the upload is accepted (pipelined, like the CLI). */
export async function enqueue(path: string): Promise<FileOutcome | PendingUpload> {
  let data: Uint8Array;
  try {
    data = await readFile(path);
  } catch (exc) {
    return { kind: "failed", detail: `failed: ${exc}`, retryable: true };
  }
  const form = new FormData();
  form.append("file", new Blob([data.buffer as ArrayBuffer], { type: "application/json" }), basename(path));
  let res: Response;
  try {
    res = await request("/v1/uploads", { method: "POST", body: form });
  } catch (exc) {
    return { kind: "failed", detail: `failed: ${exc}`, retryable: true };
  }

  if (res.status === 201) {
    const body = await res.json();
    return { path, uploadId: body.upload_id, deadline: Date.now() + POLL_TIMEOUT_MS };
  }
  const error = await errorBody(res);
  if (res.status === 409 && error.code === "duplicate_upload") {
    return { kind: "skipped", detail: "already synced", retryable: false };
  }
  return { kind: "failed", detail: `failed: ${error.message}`, retryable: false };
}

/** One status poll: a terminal outcome, or null while still ingesting. */
export async function check(pending: PendingUpload): Promise<FileOutcome | null> {
  if (Date.now() >= pending.deadline) {
    return {
      kind: "failed",
      detail:
        `failed: ingestion not finished after ${POLL_TIMEOUT_MS / 1000}s ` +
        `(check /uploads for upload ${pending.uploadId})`,
      retryable: false,
    };
  }
  let res: Response;
  try {
    res = await request(`/v1/uploads/${pending.uploadId}`);
  } catch (exc) {
    // The upload itself landed; a retry dedupes to "already synced" rather
    // than leaving the file silently dropped.
    return { kind: "failed", detail: `failed: status poll error: ${exc}`, retryable: true };
  }
  if (res.status !== 200) {
    const error = await errorBody(res);
    return { kind: "failed", detail: `failed: status poll: ${error.message}`, retryable: false };
  }
  const body = await res.json();
  if (body.status === "complete") {
    const count = body.trace_ids.length;
    return {
      kind: "uploaded",
      detail: `uploaded (complete, ${count} trace${count === 1 ? "" : "s"})`,
      retryable: false,
    };
  }
  if (body.status === "failed") {
    return { kind: "failed", detail: `failed: ${body.error_message}`, retryable: false };
  }
  return null;
}
