"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, ChevronRight, X } from "lucide-react";
import { OutcomeBadge } from "@/components/traces/badges";
import { Pager, usePageParam } from "@/components/shell/pager";
import { listReviewItems, type ReviewItem, type ReviewItemList } from "@/lib/api/review";
import { formatDate } from "@/lib/format";
import { useRealtimeRefetch } from "@/lib/realtime";
import { humanize } from "@/components/review/taxonomy";

function Row({ item, uploadFilter }: { item: ReviewItem; uploadFilter: string | null }) {
  const verdict = item.context.verdict;
  const href = uploadFilter
    ? `/review/${item.review_item_id}?upload_id=${uploadFilter}`
    : `/review/${item.review_item_id}`;
  return (
    <Link href={href} className="block px-4 py-3 transition-colors hover:bg-accent/50">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-sm font-medium">{item.trace.name}</span>
          {verdict.outcome ? (
            <OutcomeBadge
              outcome={verdict.outcome}
              confidence={verdict.outcome_confidence}
              provenance="machine"
            />
          ) : (
            <span className="text-xs text-muted-foreground">no machine verdict</span>
          )}
          {verdict.task_category && (
            <span className="hidden text-xs text-muted-foreground sm:inline">
              {humanize(verdict.task_category)}
              {verdict.task_category_confidence !== null && (
                <span className="ml-1 font-mono">
                  {verdict.task_category_confidence.toFixed(2)}
                </span>
              )}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <time>{formatDate(item.created_at)}</time>
          <ChevronRight className="size-3.5" />
        </div>
      </div>
      {item.context.reasons.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          {item.context.reasons.map((r) => r.message).join(" ")}
        </p>
      )}
      {item.context.reasons.length === 0 && (
        <p className="mt-1 text-xs text-muted-foreground">Relabel requested by you.</p>
      )}
    </Link>
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
            <Row key={item.review_item_id} item={item} uploadFilter={uploadFilter} />
          ))
        ) : (
          <details key={`${group.uploadId}-${group.items[0].review_item_id}`} open>
            <summary className="cursor-pointer px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground">
              {group.items.length} from upload{" "}
              <span className="font-medium text-foreground">{group.filename}</span>
            </summary>
            <div className="divide-y border-t pl-4">
              {group.items.map((item) => (
                <Row key={item.review_item_id} item={item} uploadFilter={uploadFilter} />
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
        Traces the analyzers were uncertain about. Reviewing improves labels — it gates nothing.
      </p>

      {uploadFilter && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-0.5 text-xs">
            {/* An empty filtered queue has no row to name the upload from. */}
            upload: {result?.items[0]?.upload_filename ?? `${uploadFilter.slice(0, 8)}…`}
            <Link href="/review" aria-label="Clear upload filter" className="hover:text-foreground">
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
              When the judge is uncertain about a trace, it lands here.
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
