import { load } from "@tauri-apps/plugin-store";

// Persisted synced-file marks (path → "size:mtime") so a restart's initial
// sync only offers files that are new or changed since the last run, instead
// of re-uploading everything for the server to answer duplicate_upload.
// Entries are scoped per server + account: a cache hit must never suppress an
// upload the current backend hasn't seen. Misses are always safe — the file
// just takes the normal upload → server-dedupe path.

const STORE_FILE = "sync-cache.json";

export type SyncedStore = {
  entries: Map<string, string>;
  save(): Promise<void>;
};

export async function openSyncCache(apiUrl: string, userId: string): Promise<SyncedStore> {
  const store = await load(STORE_FILE);
  const scope = `${apiUrl}::${userId}`;
  const entries = new Map(Object.entries((await store.get<Record<string, string>>(scope)) ?? {}));
  return {
    entries,
    save: async () => {
      await store.set(scope, Object.fromEntries(entries));
      await store.save();
    },
  };
}

/** Sign-out wipes every scope: a different account — or the same account
 *  against a re-seeded backend — must start from a clean slate. */
export async function clearSyncCache(): Promise<void> {
  const store = await load(STORE_FILE);
  await store.clear();
  await store.save();
}
