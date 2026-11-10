import { publicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";

// Mirrors the API's error envelope (services/api/app/errors.py).
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

/** A readable message for a failed call. Request-validation 422s carry the
 *  useful text in `details.errors[].msg`, so those are shown verbatim. */
export function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const errors = err.details.errors;
  if (Array.isArray(errors)) {
    const messages = errors
      .map((e) => (typeof e === "object" && e !== null && "msg" in e ? String(e.msg) : null))
      .filter((m): m is string => m !== null);
    if (messages.length > 0) return messages.join(" ");
  }
  return err.message;
}

const GET_RETRIES = 3;

async function authedRequest(path: string, init?: RequestInit): Promise<Response> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers = new Headers(init?.headers);
  if (session) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  // FormData bodies set their own multipart boundary; don't override.
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const method = (init?.method ?? "GET").toUpperCase();
  let res = await fetch(`${publicEnv.apiUrl}${path}`, { ...init, headers });
  // Rate limited: GETs back off and retry (Retry-After when the API sends it,
  // else 1s, 2s, 4s); writes surface the 429 to the caller.
  for (let attempt = 0; res.status === 429 && method === "GET" && attempt < GET_RETRIES; attempt++) {
    const after = Number(res.headers.get("Retry-After"));
    const wait = Number.isFinite(after) && after > 0 ? after * 1000 : 1000 * 2 ** attempt;
    await new Promise((resolve) => setTimeout(resolve, Math.min(wait, 10_000)));
    res = await fetch(`${publicEnv.apiUrl}${path}`, { ...init, headers });
  }
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

// Browser-side API client (uses the browser Supabase session). Server
// components need a separate variant built on the server Supabase client.
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authedRequest(path, init);
  return res.json() as Promise<T>;
}

// For endpoints with no response body (e.g. DELETE → 204).
export async function apiSend(path: string, init?: RequestInit): Promise<void> {
  await authedRequest(path, init);
}

// Authenticated binary download (downloads need the bearer header, so a plain
// <a href> can't be used). Triggers a browser save via a temporary object URL.
export async function apiDownload(path: string, filename: string, init?: RequestInit): Promise<void> {
  const res = await authedRequest(path, init);
  const url = URL.createObjectURL(await res.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
