import { load, type Store } from "@tauri-apps/plugin-store";

export type Settings = {
  apiUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
  webUrl: string;
  folders: string[];
  sinceHours: number | null;
};

// Connection defaults are injected at build time (VITE_* set by the release
// workflow, pointing at production) and fall back to the local stack
// (.env.example) for dev builds. The fallback anon key is the public
// local-dev key, not a secret; everything is editable in the Settings tab.
const LOCAL_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0";

// sinceHours defaults to 24 so a first watch of a harness's whole session
// history doesn't bulk-upload months of logs (matches the CLI demo's
// --since-hours 24 guidance); clearable in the Watch tab.
export const DEFAULT_SETTINGS: Settings = {
  apiUrl: import.meta.env.VITE_API_URL || "http://localhost:8000",
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL || "http://127.0.0.1:55321",
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || LOCAL_ANON_KEY,
  webUrl: import.meta.env.VITE_WEB_URL || "http://localhost:3000",
  folders: [],
  sinceHours: 24,
};

let store: Store | null = null;

async function settingsStore(): Promise<Store> {
  if (store === null) store = await load("settings.json");
  return store;
}

/** First run only (nothing saved yet): null signals the caller to seed
 *  defaults — e.g. auto-adding detected harness session folders. */
export async function loadSavedSettings(): Promise<Settings | null> {
  const s = await settingsStore();
  const saved = await s.get<Partial<Settings>>("settings");
  if (saved === undefined || saved === null) return null;
  return { ...DEFAULT_SETTINGS, ...saved };
}

export async function saveSettings(settings: Settings): Promise<void> {
  const s = await settingsStore();
  await s.set("settings", settings);
  await s.save();
}
