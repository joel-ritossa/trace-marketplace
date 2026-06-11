import { apiFetch, apiSend } from "@/lib/api/client";
import type { TraceFilters, TraceListItem } from "@/lib/api/traces";

// Types mirror services/api/app/schemas/subscription.py — keep in sync.

export type Subscription = {
  subscription_id: string;
  name: string;
  // The stored filter map — the same vocabulary as TraceFilters.
  query: TraceFilters;
  // Behavior anchor (docs/proposals/similar-behavior.md): match requires
  // cosine similarity to this trace ≥ threshold, ANDed with the query.
  similar_to_trace_id: string | null;
  similarity_threshold: number | null;
  // Anchor trace's name for display; null when the anchor was deleted.
  similar_to_name: string | null;
  created_at: string;
  last_seen_at: string;
  match_count: number;
  last_match_at: string | null;
};

export type SubscriptionAnchor = { traceId: string; threshold: number };

export type SubscriptionFeedItem = TraceListItem & { new_since_last_seen: boolean };

export type SubscriptionFeed = {
  traces: SubscriptionFeedItem[];
  total: number;
  excluded_unanalyzed: number | null;
};

export async function listSubscriptions(): Promise<Subscription[]> {
  const { subscriptions } = await apiFetch<{ subscriptions: Subscription[] }>("/v1/subscriptions");
  return subscriptions;
}

export async function createSubscription(
  name: string,
  query: TraceFilters,
  anchor?: SubscriptionAnchor,
): Promise<Subscription> {
  return apiFetch<Subscription>("/v1/subscriptions", {
    method: "POST",
    body: JSON.stringify({
      name,
      query,
      ...(anchor && {
        similar_to_trace_id: anchor.traceId,
        similarity_threshold: anchor.threshold,
      }),
    }),
  });
}

export async function updateSubscription(
  id: string,
  patch: {
    name?: string;
    query?: TraceFilters;
    // The anchor pair patches as a unit: an object sets it, null clears it.
    anchor?: SubscriptionAnchor | null;
  },
): Promise<Subscription> {
  const { anchor, ...rest } = patch;
  const body: Record<string, unknown> = { ...rest };
  if (anchor !== undefined) {
    body.similar_to_trace_id = anchor?.traceId ?? null;
    body.similarity_threshold = anchor?.threshold ?? null;
  }
  return apiFetch<Subscription>(`/v1/subscriptions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteSubscription(id: string): Promise<void> {
  await apiSend(`/v1/subscriptions/${id}`, { method: "DELETE" });
}

export async function subscriptionResults(
  id: string,
  limit = 25,
  offset = 0,
): Promise<SubscriptionFeed> {
  return apiFetch<SubscriptionFeed>(
    `/v1/subscriptions/${id}/results?limit=${limit}&offset=${offset}`,
  );
}

export async function markSubscriptionSeen(id: string): Promise<void> {
  await apiSend(`/v1/subscriptions/${id}/seen`, { method: "POST" });
}

/** The query map sent to the API: only the active predicates, so the
 *  stored map (and the chips rendered from it) is exactly what was saved. */
export function cleanQuery(filters: TraceFilters): TraceFilters {
  const query: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "") continue;
    if (key === "has_errors" && value === false) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    query[key] = value;
  }
  return query as TraceFilters;
}
