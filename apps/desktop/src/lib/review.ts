import { apiFetch } from "./api";

// Types mirror services/api/app/schemas/review.py and the web's
// lib/api/review.ts — keep in sync.

export type TraceStatus = "ok" | "error";
export type Outcome = "success" | "failure" | "indeterminate";
export type Provenance = "machine" | "human_confirmed" | "human";

export type ReviewStatus = "open" | "resolved" | "superseded";
export type ReviewListStatus = ReviewStatus | "all";

export type ReviewVerdictContext = {
  outcome: Outcome | null;
  outcome_confidence: number | null;
  failure_mode: string | null;
  failure_mode_confidence: number | null;
  task_category: string | null;
  task_category_confidence: number | null;
};

export type ReviewReason = { code: string; message: string };

export type ReviewContext = {
  verdict: ReviewVerdictContext;
  // Empty = owner-initiated relabel.
  reasons: ReviewReason[];
};

export type ReviewAnswer = {
  outcome: Outcome | null;
  failure_mode: string | null;
  task_category: string | null;
};

export type ReviewTraceSummary = {
  trace_id: string;
  name: string;
  status: TraceStatus;
  started_at: string;
  duration_ms: number;
};

export type ReviewItem = {
  review_item_id: string;
  trace_id: string;
  upload_id: string;
  upload_filename: string;
  question_type: string;
  context: ReviewContext;
  status: ReviewStatus;
  created_at: string;
  trace: ReviewTraceSummary;
  answer: ReviewAnswer | null;
  resolved_at: string | null;
  resolved_by: string | null;
};

export type ReviewItemList = { items: ReviewItem[]; total: number };

export type ReviewResolveRequest = {
  outcome?: Outcome;
  failure_mode?: string;
  task_category?: string;
};

export type ResolvedLabel = { value: string; confidence: number; provenance: Provenance };

export type ReviewResolveResponse = {
  item: ReviewItem;
  labels: Record<string, ResolvedLabel>;
};

export async function getReviewItem(itemId: string): Promise<ReviewItem> {
  return apiFetch<ReviewItem>(`/v1/review-items/${itemId}`);
}

export async function listReviewItems(
  options: { status?: ReviewListStatus; uploadId?: string; limit?: number; offset?: number } = {},
): Promise<ReviewItemList> {
  const params = new URLSearchParams({
    status: options.status ?? "open",
    limit: String(options.limit ?? 50),
    offset: String(options.offset ?? 0),
  });
  if (options.uploadId) params.set("upload_id", options.uploadId);
  return apiFetch<ReviewItemList>(`/v1/review-items?${params}`);
}

export async function resolveReviewItem(
  itemId: string,
  answer: ReviewResolveRequest,
): Promise<ReviewResolveResponse> {
  return apiFetch<ReviewResolveResponse>(`/v1/review-items/${itemId}/resolve`, {
    method: "POST",
    body: JSON.stringify(answer),
  });
}
