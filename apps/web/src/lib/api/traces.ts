import { ApiError, apiDownload, apiFetch, apiSend } from "@/lib/api/client";

// Types mirror services/api/app/schemas/trace.py and span.py — keep in sync.

export type TraceStatus = "ok" | "error";
export type SpanKind = "llm" | "agent" | "tool" | "chain" | "retriever" | "embedding" | "other";
export type SpanStatus = "ok" | "error" | "unset";
export type TraceSort = "created_at" | "duration_ms" | "span_count";
export type TraceScope = "mine" | "marketplace" | "acquired";
export type TraceVisibility = "private" | "listed";

export type TraceListItem = {
  trace_id: string;
  name: string;
  status: TraceStatus;
  started_at: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
  provider: string | null;
  model: string | null;
  created_at: string;
  visibility: TraceVisibility;
  tags: string[];
  description: string | null;
  listed_at: string | null;
  owner_display_name: string | null;
  is_owner: boolean;
  acquired: boolean;
  acquired_at: string | null;
};

export type TraceList = { traces: TraceListItem[]; total: number };

export type TraceDetail = {
  trace_id: string;
  upload_id: string;
  source_trace_id: string;
  name: string;
  status: TraceStatus;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
  provider: string | null;
  model: string | null;
  service_name: string | null;
  tool_names: string[];
  error_types: string[];
  tags: string[];
  description: string | null;
  visibility: TraceVisibility;
  listed_at: string | null;
  owner_display_name: string | null;
  source_format: string;
  importer_version: string;
  created_at: string;
  is_owner: boolean;
  acquired: boolean;
  can_download: boolean;
};

export type TraceFilters = {
  q?: string;
  provider?: string;
  model?: string;
  tool?: string;
  has_errors?: boolean;
  from?: string;
  to?: string;
};

export type TraceUpdate = {
  visibility?: TraceVisibility;
  tags?: string[];
  description?: string | null;
  confirm_ownership?: boolean;
};

export type Acquisition = {
  acquisition_id: string;
  trace_id: string;
  price_usd: number;
  acquired_at: string;
};

export type SpanListItem = {
  span_id: string;
  source_span_id: string;
  source_parent_span_id: string | null;
  name: string;
  kind: SpanKind;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  status: SpanStatus;
  status_message: string | null;
  error_type: string | null;
  provider: string | null;
  model: string | null;
  tool_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
};

export type SpanList = { spans: SpanListItem[]; total: number };

export type SpanEvent = {
  name: string;
  timestamp: string | null;
  attributes: Record<string, unknown>;
};

export type SpanDetail = SpanListItem & {
  attributes: Record<string, unknown>;
  events: SpanEvent[];
};

export const SPAN_PAGE_SIZE = 500;

export async function listTraces(
  scope: TraceScope = "mine",
  sort: TraceSort = "created_at",
  filters: TraceFilters = {},
): Promise<TraceList> {
  const params = new URLSearchParams({ scope, sort });
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "" && value !== false) params.set(key, String(value));
  }
  return apiFetch<TraceList>(`/v1/traces?${params}`);
}

export async function getTrace(traceId: string): Promise<TraceDetail> {
  return apiFetch<TraceDetail>(`/v1/traces/${traceId}`);
}

export async function updateTrace(traceId: string, update: TraceUpdate): Promise<TraceDetail> {
  return apiFetch<TraceDetail>(`/v1/traces/${traceId}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}

export async function deleteTrace(traceId: string): Promise<void> {
  await apiSend(`/v1/traces/${traceId}`, { method: "DELETE" });
}

export async function acquireTrace(traceId: string): Promise<Acquisition> {
  return apiFetch<Acquisition>(`/v1/traces/${traceId}/acquire`, { method: "POST" });
}

/** Pages through the light span list until the whole trace is loaded.
 *  onProgress reports (loaded, total) so big traces can show progress.
 *
 *  Draining a huge trace can outrun the API's per-user rate limit (10/s,
 *  burst 20 — ~10k spans), so 429s back off and retry instead of failing
 *  the whole load. Bounded: a second of refill covers many more pages. */
export async function listAllSpans(
  traceId: string,
  onProgress?: (loaded: number, total: number) => void,
): Promise<SpanListItem[]> {
  const all: SpanListItem[] = [];
  let retries = 0;
  for (;;) {
    let page: SpanList;
    try {
      page = await apiFetch<SpanList>(
        `/v1/traces/${traceId}/spans?limit=${SPAN_PAGE_SIZE}&offset=${all.length}`,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 429 && retries < 5) {
        retries += 1;
        await new Promise((resolve) => setTimeout(resolve, 1100));
        continue;
      }
      throw err;
    }
    retries = 0;
    all.push(...page.spans);
    onProgress?.(all.length, page.total);
    if (all.length >= page.total || page.spans.length === 0) return all;
  }
}

export async function getSpan(traceId: string, spanId: string): Promise<SpanDetail> {
  return apiFetch<SpanDetail>(`/v1/traces/${traceId}/spans/${spanId}`);
}

export async function downloadTrace(traceId: string, filename: string): Promise<void> {
  return apiDownload(`/v1/traces/${traceId}/download`, filename);
}
