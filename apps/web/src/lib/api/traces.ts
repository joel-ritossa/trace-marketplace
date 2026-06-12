import { ApiError, apiDownload, apiFetch, apiSend } from "@/lib/api/client";

// Types mirror services/api/app/schemas/trace.py and span.py — keep in sync.

export type TraceStatus = "ok" | "error";
export type SpanKind = "llm" | "agent" | "tool" | "chain" | "retriever" | "embedding" | "other";
export type SpanStatus = "ok" | "error" | "unset";
export type TraceSort = "created_at" | "duration_ms" | "span_count";
export type TraceScope = "mine" | "marketplace" | "acquired";
export type TraceVisibility = "private" | "listed";

// Analysis vocabulary (schemas/analysis.py).
export type Outcome = "success" | "failure" | "indeterminate";
export type Provenance = "machine" | "human_confirmed" | "human";
export type AnalysisState = "pending" | "complete" | "skipped" | "failed";
export type SkipReason = "not_configured" | "owner_opt_out";

type AnalysisFields = {
  outcome: Outcome | null;
  outcome_confidence: number | null;
  outcome_provenance: Provenance | null;
  analysis_state: AnalysisState;
  // Owner-only (A3): always false/null on a non-owner's card.
  has_open_review_item: boolean;
  open_review_item_id: string | null;
};

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
} & AnalysisFields;

export type TraceList = {
  traces: TraceListItem[];
  total: number;
  // Set when analysis predicates are active: traces matching the other
  // filters that have no analysis row yet (the filter-exclusion note).
  excluded_unanalyzed: number | null;
};

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
  total_tokens: number | null;
} & AnalysisFields;

export type LabelValue = {
  value: string;
  confidence: number | null;
  provenance: Provenance;
};

export type TraceAnalysis = {
  analysis_state: AnalysisState;
  skip_reason: SkipReason | null;
  failed_reason: string | null;
  labels: {
    outcome: LabelValue | null;
    failure_mode: LabelValue | null;
    task_category: LabelValue | null;
  };
  summary: { gist: string | null; steps: string[] } | null;
  reasoning: string | null;
  signals: {
    has_retry_loop: boolean | null;
    loop_kind: string | null;
    recovered_from_error: boolean | null;
    truncation_suspected: boolean | null;
    llm_call_count: number | null;
    tool_call_count: number | null;
  } | null;
  metric_scores: Record<string, number | boolean> | null;
  open_review_item_id: string | null;
  audit: {
    analyzers: {
      analyzer: string;
      analyzer_version: string;
      model_id: string | null;
      confidence: number | null;
      votes: Record<string, unknown>[] | null;
      rendering_truncated: boolean | null;
    }[];
  };
};

// The full filter vocabulary (schemas/trace.py TraceFilterQuery) — also the
// subscription query language. Equality fields take comma-separated values
// (OR within a field); metric entries are "<name>:<min>" or "<name>:true".
export type TraceFilters = {
  q?: string;
  provider?: string;
  model?: string;
  tool?: string;
  has_errors?: boolean;
  from?: string;
  to?: string;
  outcome?: string;
  failure_mode?: string;
  task_category?: string;
  loop_kind?: string;
  outcome_provenance?: string;
  failure_mode_provenance?: string;
  task_category_provenance?: string;
  has_retry_loop?: boolean;
  recovered_from_error?: boolean;
  truncation_suspected?: boolean;
  outcome_confidence_gte?: number;
  task_category_confidence_gte?: number;
  duration_ms_gte?: number;
  total_tokens_gte?: number;
  llm_call_count_gte?: number;
  tool_call_count_gte?: number;
  metric?: string[];
};

/** Filter params for a request or URL. Booleans: has_errors only filters
 *  when true; the signal booleans filter on both values. */
export function filterParams(filters: TraceFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "") continue;
    if (key === "has_errors" && value === false) continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item);
    } else {
      params.set(key, String(value));
    }
  }
  return params;
}

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
  limit = 25,
  offset = 0,
): Promise<TraceList> {
  const params = filterParams(filters);
  params.set("scope", scope);
  params.set("sort", sort);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch<TraceList>(`/v1/traces?${params}`);
}

export async function listMetricKeys(): Promise<string[]> {
  const { keys } = await apiFetch<{ keys: string[] }>("/v1/traces/metric-keys");
  return keys;
}

// Bulk operations (3_api.md): ≤100 ids, itemized results — partial success
// is normal.

export type BulkAcquireStatus =
  | "acquired"
  | "already_acquired"
  | "not_listed"
  | "not_found";

export type BulkAcquireResult = { trace_id: string; status: BulkAcquireStatus }[];

export async function bulkAcquire(traceIds: string[]): Promise<BulkAcquireResult> {
  const { results } = await apiFetch<{ results: BulkAcquireResult }>("/v1/traces/acquire", {
    method: "POST",
    body: JSON.stringify({ trace_ids: traceIds }),
  });
  return results;
}

export type BulkVisibilityResult = { trace_id: string; status: "updated" | "not_found" }[];

export async function bulkVisibility(
  traceIds: string[],
  visibility: TraceVisibility,
  confirmOwnership = false,
): Promise<BulkVisibilityResult> {
  const { results } = await apiFetch<{ results: BulkVisibilityResult }>("/v1/traces/visibility", {
    method: "POST",
    body: JSON.stringify({
      trace_ids: traceIds,
      visibility,
      confirm_ownership: confirmOwnership,
    }),
  });
  return results;
}

export async function bulkDownload(traceIds: string[]): Promise<void> {
  await apiDownload(`/v1/traces/download`, `traces-${traceIds.length}.zip`, {
    method: "POST",
    body: JSON.stringify({ trace_ids: traceIds }),
  });
}

export async function getTrace(traceId: string): Promise<TraceDetail> {
  return apiFetch<TraceDetail>(`/v1/traces/${traceId}`);
}

// Similar behavior (docs/proposals/similar-behavior.md): cosine neighbors
// over the embedding of the trace's analysis rendering.

export type SimilarTraceItem = TraceListItem & { similarity: number };

export type SimilarTraces = {
  // False when the anchor has no embedding yet (analysis pending, keyless
  // stack, or private without LLM consent).
  anchor_embedded: boolean;
  items: SimilarTraceItem[];
  // Count of visible traces at/above min_similarity, when it was sent.
  total_above: number | null;
};

export async function getSimilarTraces(
  traceId: string,
  opts: { limit?: number; minSimilarity?: number } = {},
): Promise<SimilarTraces> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.minSimilarity !== undefined) params.set("min_similarity", String(opts.minSimilarity));
  const qs = params.size > 0 ? `?${params}` : "";
  return apiFetch<SimilarTraces>(`/v1/traces/${traceId}/similar${qs}`);
}

export async function getTraceAnalysis(traceId: string): Promise<TraceAnalysis> {
  return apiFetch<TraceAnalysis>(`/v1/traces/${traceId}/analysis`);
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
