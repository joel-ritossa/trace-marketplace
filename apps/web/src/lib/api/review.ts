import { apiFetch } from "@/lib/api/client";
import type { TraceStatus } from "@/lib/api/traces";

// Types mirror services/api/app/schemas/review.py — keep in sync.

export type ReviewStatus = "open" | "resolved" | "superseded";
export type ReviewListStatus = ReviewStatus | "all";

/** An uncertain machine turn and why the agent could not judge it. */
export type ReviewTurn = { turn_index: number; reason: string; summary: string | null };

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
  context: { turns: ReviewTurn[] };
  status: ReviewStatus;
  created_at: string;
  trace: ReviewTraceSummary;
  // Set when the owner's relabels left no uncertain turn.
  resolved_at: string | null;
  resolved_by: string | null;
};

export type ReviewItemList = { items: ReviewItem[]; total: number };

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
