import { exists } from "@tauri-apps/plugin-fs";
import { homeDir, join } from "@tauri-apps/api/path";
import type { WatchRoot } from "./sync/files";

// The session logs coding agents already write, mirrored from
// tools/link_sessions.sh — keep in sync. First run auto-adds whichever of
// these exist; the user can remove them like any folder.
const HARNESS_SESSION_DIRS = [
  [".codex", "sessions"],
  [".claude", "projects"],
  [".cursor", "projects"],
] as const;

let harnessDirsPromise: Promise<string[]> | null = null;

/** The canonical harness dirs on this machine, existing or not (cached —
 *  path resolution is async but the answer never changes). */
function harnessDirs(): Promise<string[]> {
  harnessDirsPromise ??= (async () => {
    const home = await homeDir();
    return Promise.all(HARNESS_SESSION_DIRS.map((segments) => join(home, ...segments)));
  })();
  return harnessDirsPromise;
}

export async function detectHarnessFolders(): Promise<string[]> {
  const found: string[] = [];
  for (const dir of await harnessDirs()) {
    if (await exists(dir).catch(() => false)) found.push(dir);
  }
  return found;
}

/** Watched-folder list → watch roots. Harness dirs are restricted to
 *  `.jsonl` — session transcripts are always JSONL, and the `.json` files
 *  living next to them (Cursor MCP tool descriptors, Claude project
 *  metadata) are junk the server would reject one by one. */
export async function toWatchRoots(folders: string[]): Promise<WatchRoot[]> {
  const harness = new Set(await harnessDirs());
  return folders.map((path) =>
    harness.has(path) ? { path, suffixes: [".jsonl"] } : { path },
  );
}
