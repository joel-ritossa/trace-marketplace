"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, CircleHelp, TriangleAlert, X } from "lucide-react";
import { Pager, usePageParam } from "@/components/shell/pager";
import { AgentBadge } from "@/components/traces/badges";
import { Button } from "@/components/ui/button";
import { ExpandableText } from "@/components/ui/expandable-text";
import { analyzeTrace } from "@/lib/api/traces";
import { agentOf, cleanName, traceTitle } from "@/components/traces/names";
import { listReviewItems, type ReviewItem, type ReviewItemList } from "@/lib/api/review";
import { formatDate } from "@/lib/format";
import { useRealtimeRefetch } from "@/lib/realtime";

/** One open item: its trace's uncertain turns, each linking to that turn on
 *  the trace page, where the owner relabels it. Per turn the uncertainty
 *  reason leads; the turn's summary is secondary context. */
function Row({ item }: { item: ReviewItem }) {
  const { turns } = item.context;
  return (
    <div className="px-4 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="flex min-w-0 items-center gap-2">
          <Link
            href={`/traces/${item.trace_id}`}
            title={`First ask: ${cleanName(item.trace.name)}`}
            className="min-w-0 truncate text-sm font-medium hover:underline"
          >
            {traceTitle(item.trace.name, item.trace.goal)}
          </Link>
          {agentOf(item.trace.name) && <AgentBadge agent={agentOf(item.trace.name)!} />}
        </span>
        <p className="shrink-0 text-xs text-muted-foreground">
          {turns.length} uncertain turn{turns.length === 1 ? "" : "s"} ·{" "}
          <time className="font-mono">{formatDate(item.created_at)}</time>
        </p>
      </div>
      <ul className="mt-2 flex flex-col gap-1">
        {turns.map((turn) => (
          <li
            key={turn.turn_index}
            className="-mx-2 grid grid-cols-[4rem_minmax(0,1fr)] gap-x-3 rounded-md px-2 py-1.5 transition-colors hover:bg-accent/50"
          >
            {/* The turn label opens the turn; the reason and summary expand in place. */}
            <Link
              href={`/traces/${item.trace_id}?turn=${turn.turn_index}`}
              className="self-start rounded-sm pt-0.5 font-mono text-xs text-link-deep hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              Turn {turn.turn_index + 1}
            </Link>
            <div className="min-w-0">
              {/* Advisory, not alarm (4_pages.md): muted icon, ink reason. */}
              {isJudgeFailure(turn.reason) ? (
                // Not uncertainty: the judge errored on this turn.
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <TriangleAlert className="size-3.5 shrink-0 text-error-deep" />
                  <span className="text-error-deep">Analysis failed for this turn</span>
                  <RetryAnalysis traceId={item.trace_id} />
                </div>
              ) : (
                <div className="flex items-start gap-1.5 text-sm">
                  <CircleHelp className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <ExpandableText text={turn.reason} lines={2} className="min-w-0 flex-1" />
                </div>
              )}
              {turn.summary && (
                <ExpandableText
                  text={turn.summary}
                  lines={1}
                  className="mt-0.5 pl-5 text-xs text-muted-foreground"
                />
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// The judge's own failure marker, distinct from genuine uncertainty.
const isJudgeFailure = (reason: string) => /^The judge could not process/i.test(reason);

/** Re-run the trace's analysis (POST /analyze); the queue refreshes live. */
function RetryAnalysis({ traceId }: { traceId: string }) {
  const [state, setState] = useState<"idle" | "busy" | "queued" | "error">("idle");
  return (
    <Button
      size="xs"
      variant="outline"
      disabled={state === "busy" || state === "queued"}
      onClick={() => {
        setState("busy");
        analyzeTrace(traceId)
          .then(() => setState("queued"))
          .catch(() => setState("error"));
      }}
    >
      {state === "queued" ? "Retry queued" : state === "error" ? "Retry failed — again" : "Retry analysis"}
    </Button>
  );
}

/** Bulk syncs group by upload, mirroring the notification digest
 *  (4_pages.md). Single-item groups render flat. */
function Groups({ items, uploadFilter }: { items: ReviewItem[]; uploadFilter: string | null }) {
  const groups: { uploadId: string; filename: string; items: ReviewItem[] }[] = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.uploadId === item.upload_id) last.items.push(item);
    else groups.push({ uploadId: item.upload_id, filename: item.upload_filename, items: [item] });
  }
  return (
    <div className="divide-y rounded-lg border bg-background">
      {groups.map((group) =>
        group.items.length === 1 || uploadFilter ? (
          group.items.map((item) => (
            <Row key={item.review_item_id} item={item} />
          ))
        ) : (
          <details key={`${group.uploadId}-${group.items[0].review_item_id}`} open>
            <summary className="cursor-pointer truncate px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground">
              {group.items.length} from upload{" "}
              <span className="font-medium text-foreground" title={group.filename}>
                {group.filename}
              </span>
            </summary>
            <div className="divide-y border-t pl-4">
              {group.items.map((item) => (
                <Row key={item.review_item_id} item={item} />
              ))}
            </div>
          </details>
        ),
      )}
    </div>
  );
}

export default function ReviewQueuePage() {
  const searchParams = useSearchParams();
  const uploadFilter = searchParams.get("upload_id");
  const [result, setResult] = useState<ReviewItemList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { page, setPage, pageSize, setPageSize } = usePageParam();

  const reload = useCallback(() => {
    listReviewItems({
      status: "open",
      uploadId: uploadFilter ?? undefined,
      limit: pageSize,
      offset: (page - 1) * pageSize,
    })
      .then((res) => {
        setResult(res);
        setError(null);
      })
      .catch(() => setError("Could not load the review queue. Check the API is running."));
  }, [page, pageSize, uploadFilter]);

  useEffect(reload, [reload]);
  // New items from an analysis run (or resolutions elsewhere, e.g. the
  // desktop app) appear without a manual refresh.
  useRealtimeRefetch("review_items", reload);

  useEffect(() => {
    if (result && result.items.length === 0 && page > 1 && result.total > 0) {
      setPage(Math.max(1, Math.ceil(result.total / pageSize)));
    }
  }, [result, page, pageSize, setPage]);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <h1 className="text-2xl font-semibold tracking-tight">Review</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Turns the judge was uncertain about. Relabeling them improves labels — it gates nothing.
      </p>

      {uploadFilter && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          <span className="inline-flex max-w-full min-w-0 items-center gap-1.5 rounded-full bg-secondary px-2 py-0.5 text-xs">
            {/* An empty filtered queue has no row to name the upload from. */}
            <span className="truncate">
              upload: {result?.items[0]?.upload_filename ?? `${uploadFilter.slice(0, 8)}…`}
            </span>
            <Link
              href="/review"
              aria-label="Clear upload filter"
              className="shrink-0 rounded-full text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <X className="size-3" />
            </Link>
          </span>
        </div>
      )}

      <div className="mt-6">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : result === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : result.items.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <CheckCircle2 className="size-8 text-status-ok" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">Nothing needs review</p>
            <p className="mt-1 text-sm text-muted-foreground">
              When the judge is uncertain about a turn, its trace lands here.
            </p>
          </div>
        ) : (
          <>
            <Groups items={result.items} uploadFilter={uploadFilter} />
            <div className="mt-4">
              <Pager page={page} pageSize={pageSize} total={result.total} onPageChange={setPage} onPageSizeChange={setPageSize} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
