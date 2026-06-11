import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { fetch as tauriFetch } from "@tauri-apps/plugin-http";
import { load } from "@tauri-apps/plugin-store";
import type { Settings } from "./settings";

// One client for the app's lifetime, created after settings load (App.tsx
// reloads the window when connection settings change). The session persists
// in its own store file via the async storage adapter, so login is one-time;
// supabase-js auto-refreshes the token. HTTP goes through the Tauri-side
// fetch — the API's CORS allowlist only covers the web origin.

let client: SupabaseClient | null = null;

async function storeStorage() {
  const store = await load("auth.json");
  return {
    getItem: async (key: string) => (await store.get<string>(key)) ?? null,
    setItem: async (key: string, value: string) => {
      await store.set(key, value);
      await store.save();
    },
    removeItem: async (key: string) => {
      await store.delete(key);
      await store.save();
    },
  };
}

export async function initSupabase(settings: Settings): Promise<SupabaseClient> {
  client = createClient(settings.supabaseUrl, settings.supabaseAnonKey, {
    auth: {
      storage: await storeStorage(),
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
    },
    global: { fetch: tauriFetch },
  });
  return client;
}

export function supabase(): SupabaseClient {
  if (client === null) throw new Error("supabase client not initialized");
  return client;
}
