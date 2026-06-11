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

  const res = await fetch(`${publicEnv.apiUrl}${path}`, { ...init, headers });
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
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await authedRequest(path);
  const url = URL.createObjectURL(await res.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
