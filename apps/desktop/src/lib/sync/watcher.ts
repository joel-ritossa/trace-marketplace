import { type SyncedStore } from "./cache";
import { check, enqueue, type FileOutcome, type PendingUpload } from "./client";
import { discover, StabilityScanner, type WatchRoot } from "./files";

// The one sync loop — a TS port of apps/cli/src/trace_sync/run.py with the
// same enqueue-then-drain pipelining and re-offer rules; only the exit
// condition differs (the watcher runs until stop()). Keep in sync.

const WATCH_INTERVAL_MS = 2_000;
const DRAIN_INTERVAL_MS = 1_000;

export type Counts = { synced: number; skipped: number; failed: number };

export type WatchEvent =
  | { type: "outcome"; path: string; outcome: FileOutcome }
  | { type: "status"; message: string };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export class Watcher {
  readonly counts: Counts = { synced: 0, skipped: 0, failed: 0 };
  private stopped = false;

  constructor(
    private roots: WatchRoot[],
    private sinceHours: number | null,
    private onEvent: (event: WatchEvent) => void,
    private store: SyncedStore | null = null,
  ) {}

  stop(): void {
    this.stopped = true;
  }

  /** Initial sync pass, then upload files as they appear or change; resolves
   *  once stop() is called and the in-flight batch drains. */
  async run(): Promise<void> {
    const scanner = new StabilityScanner(this.roots, this.sinceHours, this.store);
    // Files whose persisted synced mark still matches skip the upload
    // round-trip entirely instead of being POSTed and 409-skipped.
    const discovered = await discover(this.roots, this.sinceHours);
    const initial = await scanner.unsynced(discovered);
    const cached = discovered.length - initial.length;
    const cachedNote = cached > 0 ? ` (${cached} already synced)` : "";
    this.onEvent({
      type: "status",
      message:
        initial.length > 0
          ? `initial sync: ${initial.length} file${initial.length === 1 ? "" : "s"}${cachedNote}`
          : cached > 0
            ? `all ${cached} file${cached === 1 ? "" : "s"} already synced — watching`
            : "no .json/.jsonl files yet — watching",
    });
    await this.syncAndMark(initial, scanner);
    while (!this.stopped) {
      await sleep(WATCH_INTERVAL_MS);
      if (this.stopped) break;
      await this.syncAndMark(await scanner.scan(), scanner);
    }
  }

  private async syncAndMark(files: string[], scanner: StabilityScanner): Promise<void> {
    // Transport failures stay unmarked so the scanner re-offers the file;
    // server rejections are marked — a permanently bad file must not loop.
    // Only successes/skips persist: a restart retries failed files once.
    let marked = false;
    for (const { path, outcome } of await this.syncBatch(files)) {
      if (outcome.retryable) continue;
      if (outcome.kind === "failed") {
        await scanner.markFailed(path);
      } else {
        await scanner.markSynced(path);
        marked = true;
      }
    }
    if (marked) await scanner.persist();
  }

  /** Enqueue every file, then drain the in-flight set (pipelined: ingestion
   *  runs concurrently on the server's queue; we only serialize the quick
   *  POSTs). Returns (path, outcome) per file for the re-offer logic. */
  private async syncBatch(files: string[]): Promise<{ path: string; outcome: FileOutcome }[]> {
    const results: { path: string; outcome: FileOutcome }[] = [];
    let pending: PendingUpload[] = [];
    for (const path of files) {
      // Stop must be responsive mid-batch — an initial sync can be huge, and
      // anything already enqueued completes server-side regardless.
      if (this.stopped) return results;
      const enqueued = await enqueue(path);
      if ("uploadId" in enqueued) {
        pending.push(enqueued);
      } else {
        this.record(path, enqueued);
        results.push({ path, outcome: enqueued });
      }
    }

    while (pending.length > 0 && !this.stopped) {
      const stillPending: PendingUpload[] = [];
      for (const upload of pending) {
        if (this.stopped) return results;
        const outcome = await check(upload);
        if (outcome === null) {
          stillPending.push(upload);
        } else {
          this.record(upload.path, outcome);
          results.push({ path: upload.path, outcome });
        }
      }
      pending = stillPending;
      if (pending.length > 0) await sleep(DRAIN_INTERVAL_MS);
    }
    return results;
  }

  private record(path: string, outcome: FileOutcome): void {
    if (outcome.kind === "uploaded") this.counts.synced += 1;
    else if (outcome.kind === "skipped") this.counts.skipped += 1;
    else this.counts.failed += 1;
    this.onEvent({ type: "outcome", path, outcome });
  }
}
