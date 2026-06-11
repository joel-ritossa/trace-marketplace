import { readDir, stat } from "@tauri-apps/plugin-fs";
import type { SyncedStore } from "./cache";

// Trace-file discovery and the watch-mode stability scan — a TS port of
// apps/cli/src/trace_sync/files.py, same semantics. Keep in sync.
// Two extensions over the CLI: a watch root can restrict suffixes — harness
// session dirs hold .jsonl transcripts next to .json junk (Cursor MCP
// descriptors, Claude project metadata) that must never be offered — and the
// scanner's synced marks can persist across runs (cache.ts) so restarts don't
// re-upload everything for the server to dedupe.

const ALL_SUFFIXES = [".json", ".jsonl"] as const;

export type WatchRoot = { path: string; suffixes?: readonly string[] };

function hasTraceSuffix(name: string, suffixes: readonly string[]): boolean {
  const lower = name.toLowerCase();
  return suffixes.some((s) => lower.endsWith(s));
}

export type FileStat = { size: number; mtimeMs: number };

async function statOrNull(path: string): Promise<(FileStat & { isDir: boolean }) | null> {
  try {
    const info = await stat(path);
    return {
      size: info.size,
      mtimeMs: info.mtime?.getTime() ?? -1,
      isDir: info.isDirectory,
    };
  } catch {
    return null; // vanished between listing and stat, or unreadable
  }
}

async function walk(dir: string, found: Set<string>, suffixes: readonly string[]): Promise<void> {
  let entries;
  try {
    entries = await readDir(dir);
  } catch {
    return; // unreadable directory: skip, never abort the scan
  }
  for (const entry of entries) {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory) await walk(path, found, suffixes);
    else if (entry.isFile && hasTraceSuffix(entry.name, suffixes)) found.add(path);
  }
}

/** `*.json` / `*.jsonl` files (any case, per-root restrictable) under the
 *  given roots, recursive, sorted, deduped. `sinceHours` keeps only files
 *  modified in the last N hours — file selection only, never content
 *  interpretation. */
export async function discover(
  roots: WatchRoot[],
  sinceHours: number | null = null,
): Promise<string[]> {
  const found = new Set<string>();
  for (const { path, suffixes = ALL_SUFFIXES } of roots) {
    const info = await statOrNull(path);
    if (info === null) continue;
    if (info.isDir) await walk(path, found, suffixes);
    else if (hasTraceSuffix(path, suffixes)) found.add(path);
  }
  let files = [...found];
  if (sinceHours !== null) {
    const cutoff = Date.now() - sinceHours * 3600 * 1000;
    const kept: string[] = [];
    for (const path of files) {
      const info = await statOrNull(path);
      if (info !== null && info.mtimeMs >= cutoff) kept.push(path);
    }
    files = kept;
  }
  return files.sort();
}

/** Tracks (size, mtime) across scans so watch only uploads files that have
 *  stopped growing (the CLI spec's debounce). The synced marks optionally
 *  live in a persisted store (per server + account) so the next run's
 *  initial sync skips unchanged files; server dedupe remains the source of
 *  truth — a missing mark just costs one upload round-trip. */
export class StabilityScanner {
  private pending = new Map<string, string>();
  private synced: Map<string, string>;
  // Non-retryable failures: same don't-re-offer semantics as synced within a
  // run, but never persisted — a restart gives a failed file one more try.
  private failed = new Map<string, string>();

  constructor(
    private roots: WatchRoot[],
    private sinceHours: number | null = null,
    private store: SyncedStore | null = null,
  ) {
    this.synced = store?.entries ?? new Map();
  }

  /** Record the just-uploaded state so the file isn't re-offered until it
   *  changes again. */
  async markSynced(path: string): Promise<void> {
    const info = await statOrNull(path);
    if (info !== null) {
      this.synced.set(path, key(info));
      this.pending.delete(path);
    }
  }

  /** Record a server rejection — a permanently bad file must not loop. */
  async markFailed(path: string): Promise<void> {
    const info = await statOrNull(path);
    if (info !== null) {
      this.failed.set(path, key(info));
      this.pending.delete(path);
    }
  }

  /** Flush the synced marks to the persisted store (no-op when stateless).
   *  Called once per upload batch, not per file. */
  async persist(): Promise<void> {
    await this.store?.save();
  }

  /** Paths whose current stats differ from their synced mark — the initial
   *  pass uses this so already-synced files skip the upload entirely. */
  async unsynced(paths: string[]): Promise<string[]> {
    const out: string[] = [];
    for (const path of paths) {
      const info = await statOrNull(path);
      if (info !== null && this.synced.get(path) !== key(info)) out.push(path);
    }
    return out;
  }

  /** One tick: files whose stats are new/changed vs the synced/failed marks
   *  and unchanged since the previous tick (stable) are ready to upload. */
  async scan(): Promise<string[]> {
    const ready: string[] = [];
    const present = new Set(await discover(this.roots, this.sinceHours));
    for (const path of present) {
      const info = await statOrNull(path);
      if (info === null) continue;
      if (this.synced.get(path) === key(info) || this.failed.get(path) === key(info)) continue;
      if (this.pending.get(path) === key(info)) ready.push(path);
      else this.pending.set(path, key(info));
    }
    // Drop state for deleted files so a long watch doesn't grow forever.
    for (const map of [this.pending, this.synced, this.failed]) {
      for (const path of map.keys()) if (!present.has(path)) map.delete(path);
    }
    return ready.sort();
  }
}

function key(info: FileStat): string {
  return `${info.size}:${info.mtimeMs}`;
}
