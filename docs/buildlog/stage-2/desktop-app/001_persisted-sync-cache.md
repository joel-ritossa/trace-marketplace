# Pass 001 — persisted sync cache

## Problem

The watcher was deliberately stateless: every app launch re-POSTed the full
bytes of every file in the watch window and let the server answer
`409 duplicate_upload`. Correct, but full upload bandwidth per file per launch
just to learn "already have it".

## Change

Persist the `StabilityScanner` synced marks (path → `size:mtime`) across runs.
Desktop only — the CLI stays stateless (one-shot tool, restart cost is moot).

- `src/lib/sync/cache.ts` (new): Tauri store `sync-cache.json`, entries scoped
  by `apiUrl::userId` so a cache hit can never suppress an upload the current
  backend hasn't seen. Cleared on `SIGNED_OUT` (App.tsx) — account switches and
  re-seeded backends start clean.
- `StabilityScanner` accepts an optional store; the synced map is its entries.
  New `unsynced()` filters the initial discover pass, new `persist()` flushes
  once per upload batch (not per file).
- Non-retryable *failures* now go to a separate in-memory `failed` map with the
  same don't-re-offer semantics within a run, but never persisted — a restart
  gives a failed file one more try. (Before, failures shared the synced map;
  persisting that would have made a transient ingestion failure permanent.)
- Initial-sync status line reports the cached count, e.g.
  `initial sync: 3 files (212 already synced)`.

Misses stay safe: anything not in the cache takes the normal upload →
server-dedupe path. Server content hash remains the source of truth.

## Verification

`tsc --noEmit` clean. Manual check: start watch (initial sync uploads/skips),
restart app, start watch again → "already synced" count, no uploads; touch a
file → re-offered; sign out/in → full re-sync, server dedupes.
