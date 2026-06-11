import { fetch as tauriFetch } from "@tauri-apps/plugin-http";
import { supabase } from "./supabase";

// Mirrors apps/web/src/lib/api/client.ts (same error envelope) — keep in
// sync. Requests run through the Tauri-side fetch to bypass webview CORS.

export type ApiErrorBody = {
  error: { code: string; message: string; details: Record<string, unknown> };
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let baseUrl = "http://localhost:8000";

export function setApiBaseUrl(url: string): void {
  baseUrl = url.replace(/\/$/, "");
}

/** Authed request returning the raw Response (no throw on non-2xx) — the
 *  sync client needs status-code-level control (409 dedupe, 429 backoff). */
export async function apiRequest(path: string, init?: RequestInit): Promise<Response> {
  const {
    data: { session },
  } = await supabase().auth.getSession();

  const headers = new Headers(init?.headers);
  if (session) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return tauriFetch(`${baseUrl}${path}`, { ...init, headers });
}

async function authedRequest(path: string, init?: RequestInit): Promise<Response> {
  const res = await apiRequest(path, init);
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      body?.error.code ?? "unknown",
      body?.error.message ?? `API request failed with status ${res.status}`,
      body?.error.details ?? {},
    );
  }
  return res;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authedRequest(path, init);
  return res.json() as Promise<T>;
}

export async function apiSend(path: string, init?: RequestInit): Promise<void> {
  await authedRequest(path, init);
}
