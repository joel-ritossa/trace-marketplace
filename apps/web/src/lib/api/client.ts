import { publicEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";
import type { ApiErrorBody } from "@/lib/api/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Browser-side API client (uses the browser Supabase session). Server
// components need a separate variant built on the server Supabase client.
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers = new Headers(init?.headers);
  if (session) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${publicEnv.apiUrl}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      body?.error.code ?? "unknown",
      body?.error.message ?? `API request failed with status ${res.status}`,
    );
  }
  return res.json() as Promise<T>;
}
