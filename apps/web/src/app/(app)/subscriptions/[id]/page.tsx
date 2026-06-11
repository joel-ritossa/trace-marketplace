"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Hourglass } from "lucide-react";
import { Pager, usePageParam } from "@/components/shell/pager";
import { BulkAcquireAction } from "@/components/traces/bulk-actions";
import { BulkBar, useSelection } from "@/components/traces/bulk-bar";
import { ExcludedNote } from "@/components/traces/excluded-note";
import { FilterChips } from "@/components/traces/filter-chips";
import { BehaviorAnchor } from "@/components/traces/similar-traces";
import { TraceList } from "@/components/traces/trace-list";
import { ApiError } from "@/lib/api/client";
import {
  cleanQuery,
  listSubscriptions,
  markSubscriptionSeen,
  subscriptionResults,
  updateSubscription,
  type Subscription,
  type SubscriptionAnchor,
  type SubscriptionFeed,
} from "@/lib/api/subscriptions";
import type { TraceFilters } from "@/lib/api/traces";

export default function SubscriptionFeedPage() {
  const { id } = useParams<{ id: string }>();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [feed, setFeed] = useState<SubscriptionFeed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const { page, setPage, pageSize, setPageSize } = usePageParam();
  const { selected, toggle, setAll, clear } = useSelection();
  const seenStamped = useRef(false);

  useEffect(() => {
    listSubscriptions()
      .then((subs) => {
        const found = subs.find((s) => s.subscription_id === id);
        if (found) setSub(found);
        else setError("Subscription not found.");
      })
      .catch(() => setError("Could not load the subscription. Check the API is running."));
  }, [id]);

  const loadFeed = useCallback(() => {
    subscriptionResults(id, pageSize, (page - 1) * pageSize)
      .then((res) => {
        setFeed(res);
        setError(null);
        // The current view keeps its new-since markers; the next visit
        // starts counting from now.
        if (!seenStamped.current) {
          seenStamped.current = true;
          markSubscriptionSeen(id).catch(() => {});
        }
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Subscription not found."
            : "Could not load the feed. Check the API is running.",
        ),
      );
  }, [id, page, pageSize]);

  useEffect(loadFeed, [loadFeed]);

  // Editing the query (chip removal) visibly re-runs the feed (4_pages.md).
  async function onQueryChange(query: TraceFilters) {
    if (sub === null) return;
    // A subscribe-to-everything subscription is a footgun (the API rejects
    // an empty query too); the behavior anchor counts as a predicate.
    if (Object.keys(cleanQuery(query)).length === 0 && sub.similar_to_trace_id === null) {
      setQueryError("A subscription needs at least one filter — delete it instead.");
      return;
    }
    setQueryError(null);
    try {
      setSub(await updateSubscription(sub.subscription_id, { query }));
      setFeed(null);
      loadFeed();
    } catch (err) {
      setQueryError(err instanceof ApiError ? err.message : "Could not update the query.");
    }
  }

  // Behavior anchor edits (threshold slider / removal) re-run the feed too.
  async function onAnchorChange(anchor: SubscriptionAnchor | null) {
    if (sub === null) return;
    if (anchor === null && Object.keys(cleanQuery(sub.query)).length === 0) {
      setQueryError("A subscription needs at least one filter or anchor — delete it instead.");
      return;
    }
    setQueryError(null);
    try {
      setSub(await updateSubscription(sub.subscription_id, { anchor }));
      setFeed(null);
      loadFeed();
    } catch (err) {
      setQueryError(err instanceof ApiError ? err.message : "Could not update the anchor.");
    }
  }

  const newIds = new Set(
    (feed?.traces ?? []).filter((t) => t.new_since_last_seen).map((t) => t.trace_id),
  );
  const newTraces = (feed?.traces ?? []).filter((t) => newIds.has(t.trace_id));
  const earlier = (feed?.traces ?? []).filter((t) => !newIds.has(t.trace_id));

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {sub?.name ?? "Subscription"}
          </h1>
          {sub && (
            <>
              <FilterChips filters={sub.query} onChange={onQueryChange} className="mt-2" />
              <div className="mt-2 empty:hidden">
                <BehaviorAnchor key={sub.similarity_threshold} sub={sub} onPatch={onAnchorChange} />
              </div>
              {queryError && <p className="mt-1.5 text-xs text-error-deep">{queryError}</p>}
              <p className="mt-1.5 font-mono text-xs text-muted-foreground">
                {sub.match_count} listed trace{sub.match_count === 1 ? "" : "s"} matching now
              </p>
            </>
          )}
        </div>
      </div>

      <div className="mt-6">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : feed === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : feed.traces.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <Hourglass className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No matches yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              The query is saved and watching. You’ll be notified when a newly listed trace
              matches.
            </p>
            <ExcludedNote count={feed.excluded_unanalyzed} className="mt-2" />
          </div>
        ) : (
          <>
            <ExcludedNote count={feed.excluded_unanalyzed} className="mb-2" />
            {newTraces.length > 0 && (
              <>
                <p className="mb-2 text-xs font-medium text-link-deep">
                  New since you last looked
                </p>
                <TraceList
                  traces={newTraces}
                  view="feed"
                  selection={{ selected, toggle, setAll }}
                  newIds={newIds}
                />
                {earlier.length > 0 && (
                  <p className="mb-2 mt-4 text-xs font-medium text-muted-foreground">Earlier</p>
                )}
              </>
            )}
            {earlier.length > 0 && (
              <TraceList traces={earlier} view="feed" selection={{ selected, toggle, setAll }} />
            )}
            <div className="mt-4">
              <Pager page={page} pageSize={pageSize} total={feed.total} onPageChange={setPage} onPageSizeChange={setPageSize} />
            </div>
            <BulkBar count={selected.size} onClear={clear}>
              <BulkAcquireAction
                ids={[...selected]}
                onDone={() => {
                  clear();
                  loadFeed();
                }}
              />
            </BulkBar>
          </>
        )}
      </div>
    </div>
  );
}
