import { ApiError, apiDownload, apiFetch, apiSend } from "@/lib/api/client";

// Types mirror services/api/app/schemas/{trace,span,analysis}.py — keep in sync
// (checked against the FastAPI OpenAPI schema; there is no generator).

export type TraceStatus = "ok" | "error";
export type SpanKind = "llm" | "agent" | "tool" | "chain" | "retriever" | "embedding" | "other";
export type SpanStatus = "ok" | "error" | "unset";
export type TraceSort = "created_at" | "duration_ms" | "span_count";
export type TraceScope = "mine" | "marketplace" | "acquired";
export type TraceVisibility = "private" | "listed";

// Analysis vocabulary (schemas/analysis.py, app/analysis/models.py).
export type Outcome = "success" | "partial" | "failure" | "indeterminate";
export type Provenance = "machine" | "human";
export type AnalysisStatus = "pending" | "in_progress" | "final" | "skipped";
export type SkipReason = "not_configured" | "owner_opt_out";

type AnalysisFields = {
  // The roll-up's one-line "what the user was doing" — optional until every
  // deployed API sends it.
  goal?: string | null;
  // Session roll-up labels (9_session-analysis.md).
  outcome: Outcome | null;
  task_categories: string[];
  failure_modes: string[];
  analysis_status: AnalysisStatus;
  // An open analyze dead letter: the last run failed and will not retry.
  analysis_failed: boolean;
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
  // Skills the session used (agent Skill calls + user slash commands).
  // Optional until every deployed API sends it.
  skill_names?: string[];
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
  analysis: TraceAnalysis;
  // Optional until every deployed API sends them: one entry per use,
  // chronological.
  skill_names?: string[];
  skills?: SkillUse[];
  // Optional until every deployed API sends it; zeros when none.
  subagents?: SubagentSummary;
};

export type SubagentSummary = { count: number; turns: number; max_depth: number };

/** One subagent spawn (GET /v1/traces/{id}/agents), chronological. Ids are
 *  source span ids; totals cover everything under the spawn, own_span_count
 *  only its own stream. */
export type AgentSpawn = {
  span_id: string;
  parent_span_id: string | null;
  turn_index: number | null;
  depth: number;
  description: string | null;
  type: string | null;
  model: string | null;
  background: boolean | null;
  linked: boolean;
  status: "ok" | "error";
  started_at: string;
  ended_at: string;
  span_count: number;
  own_span_count: number;
  llm_calls: number;
  tool_calls: number;
  error_count: number;
  input_tokens: number;
  output_tokens: number;
};

export async function listAgents(traceId: string): Promise<AgentSpawn[]> {
  return (await apiFetch<{ agents: AgentSpawn[] }>(`/v1/traces/${traceId}/agents`)).agents;
}

/** One skill use: the agent's Skill tool call or the user's slash command.
 *  span_id is the source span id (the Skill span, or the turn span for a
 *  user-invoked skill). */
export type SkillUse = {
  name: string;
  // Null when the trace doesn't say who invoked it / which turn it was in.
  source: "agent" | "user" | null;
  turn_index: number | null;
  span_id: string;
};

export type AnalysisSignals = {
  has_retry_loop: boolean | null;
  loop_kind: string | null;
  recovered_from_error: boolean | null;
  truncation_suspected: boolean | null;
  llm_call_count: number | null;
  tool_call_count: number | null;
};

export type TurnLabel = {
  field: "task_category" | "failure_mode";
  value: string;
  // source_span_id of the spans that show it (failure modes).
  span_ids: string[];
  reason: string | null;
};

export type TurnAnalysis = {
  turn_index: number;
  // Null = not judged (LLM analysis skipped).
  outcome: Outcome | null;
  summary: string | null;
  // Why the agent could not judge confidently; null when it could.
  uncertain: string | null;
  provenance: Provenance;
  signals: AnalysisSignals;
  labels: TurnLabel[];
  // `turn.origin` on the turn span (absent = human); optional until deployed.
  origin?: "human" | "automated";
};

export type SessionAnalysis = {
  status: AnalysisStatus;
  // Every turn in the trace, judged or not.
  turn_count: number;
  skip_reason: SkipReason | null;
  goal: string | null;
  outcome: Outcome | null;
  summary: string | null;
  task_categories: string[];
  failure_modes: string[];
  analyzed_at: string | null;
  signals: AnalysisSignals | null;
};

export type TraceAnalysis = {
  session: SessionAnalysis;
  turns: TurnAnalysis[];
  failed_reason: string | null;
  // Owner-only: null for non-owners and when nothing is open.
  open_review_item_id: string | null;
};

// PUT /v1/traces/{id}/turns/{turn_index}/labels: the turn's full label set.
export type TurnLabelsRequest = {
  outcome: Outcome;
  task_categories: string[];
  failure_modes: { value: string; span_ids?: string[]; reason?: string | null }[];
};

// The full filter vocabulary (schemas/trace.py TraceFilterQuery) — also the
// subscription query language. Equality fields take comma-separated values
// (OR within a field; task_category / failure_mode match when the session
// set contains any).
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
  // Session fact, not a judge label: any of these skills (CSV, OR).
  skill?: string;
  loop_kind?: string;
  has_retry_loop?: boolean;
  recovered_from_error?: boolean;
  truncation_suspected?: boolean;
  duration_ms_gte?: number;
  total_tokens_gte?: number;
  llm_call_count_gte?: number;
  tool_call_count_gte?: number;
};

/** Filter params for a request or URL. Booleans: has_errors only filters
 *  when true; the signal booleans filter on both values. */
export function filterParams(filters: TraceFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "") continue;
    if (key === "has_errors" && value === false) continue;
    params.set(key, String(value));
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

export type SkillValue = { name: string; trace_count: number };

/** Distinct skill names with trace counts for the filter dropdown. The path
 *  follows the backend contract under construction; adjust here only. A
 *  missing endpoint reads as "no skills" so the filter degrades quietly. */
export async function listSkillValues(scope: TraceScope): Promise<SkillValue[]> {
  try {
    const res = await apiFetch<{ skills: SkillValue[] }>(`/v1/traces/skills?scope=${scope}`);
    return [...res.skills].sort((a, b) => b.trace_count - a.trace_count);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 422)) return [];
    throw err;
  }
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

/** Owner: judge what's left and roll up now, whatever the idle state (202). */
export async function analyzeTrace(traceId: string): Promise<void> {
  await apiSend(`/v1/traces/${traceId}/analyze`, { method: "POST" });
}

/** Owner relabel of one turn; returns the refreshed analysis block. */
export async function relabelTurn(
  traceId: string,
  turnIndex: number,
  body: TurnLabelsRequest,
): Promise<TraceAnalysis> {
  return apiFetch<TraceAnalysis>(`/v1/traces/${traceId}/turns/${turnIndex}/labels`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
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
