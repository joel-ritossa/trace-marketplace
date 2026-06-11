import { ApiError, apiFetch } from "./api";

// Span types and loaders mirror the web's lib/api/traces.ts (the subset the
// conversation evidence view needs) — keep in sync.

export type SpanKind = "llm" | "agent" | "tool" | "chain" | "retriever" | "embedding" | "other";
export type SpanStatus = "ok" | "error" | "unset";

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

/** Pages through the light span list until the whole trace is loaded.
 *  onProgress reports (loaded, total) so big traces can show progress.
 *  429s back off and retry instead of failing the whole load. */
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

// The subset of the analysis response the review page needs: the judge's
// reasoning behind the verdict the item snapshot shows, plus the audit
// votes for the no-consensus fallback.
export type TraceAnalysisSummary = {
  reasoning: string | null;
  audit: { analyzers: { votes: Record<string, unknown>[] | null }[] };
};

export async function getTraceAnalysis(traceId: string): Promise<TraceAnalysisSummary> {
  return apiFetch<TraceAnalysisSummary>(`/v1/traces/${traceId}/analysis`);
}
