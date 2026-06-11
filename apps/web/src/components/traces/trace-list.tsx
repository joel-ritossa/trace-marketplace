"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, Sparkles } from "lucide-react";
import {
  LibraryBadge,
  NeedsReviewLink,
  TraceOutcome,
  VisibilityBadge,
} from "@/components/traces/badges";
import { SelectBox } from "@/components/traces/bulk-bar";
import { Button } from "@/components/ui/button";
import { downloadTrace, type TraceListItem } from "@/lib/api/traces";
import { formatDate, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Selection = {
  selected: ReadonlySet<string>;
  toggle: (id: string) => void;
  setAll: (ids: readonly string[], checked: boolean) => void;
};

export type TraceListView = "mine" | "marketplace" | "library" | "feed";

/** Detail links carry the arriving surface so back navigation is contextual
 *  (4_pages.md trace-detail layout). Mine omits it — Traces is the default. */
const FROM: Record<TraceListView, string | null> = {
  mine: null,
  marketplace: "marketplace",
  library: "library",
  feed: "subscriptions",
};

function detailHref(view: TraceListView, traceId: string): string {
  const from = FROM[view];
  return from ? `/traces/${traceId}?from=${from}` : `/traces/${traceId}`;
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cn("px-4 py-2.5 font-medium", className)}>{children}</th>;
}

function MonoTd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <td className={cn("px-4 py-2.5 font-mono text-xs text-muted-foreground", className)}>
      {children}
    </td>
  );
}

/** The unified trace list (4_pages.md): one dense row spec for every list
 *  surface — my traces, marketplace, library, subscription feeds — with
 *  scope-driven columns and actions. */
export function TraceList({
  traces,
  view,
  selection,
  newIds,
}: {
  traces: TraceListItem[];
  view: TraceListView;
  selection?: Selection;
  newIds?: ReadonlySet<string>;
}) {
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const visibleIds = traces.map((t) => t.trace_id);
  const selectedVisible = selection
    ? visibleIds.filter((id) => selection.selected.has(id)).length
    : 0;
  const allVisibleSelected = selectedVisible > 0 && selectedVisible === visibleIds.length;

  async function onDownload(trace: TraceListItem) {
    setDownloadError(null);
    try {
      await downloadTrace(trace.trace_id, `${trace.name.replaceAll("/", "_")}.json`);
    } catch {
      setDownloadError(trace.trace_id);
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-background">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            {selection && (
              <Th className="w-8 px-3">
                <SelectBox
                  checked={allVisibleSelected}
                  indeterminate={selectedVisible > 0}
                  onToggle={() => selection.setAll(visibleIds, !allVisibleSelected)}
                  label={
                    allVisibleSelected ? "Deselect all on this page" : "Select all on this page"
                  }
                />
              </Th>
            )}
            <Th>Name</Th>
            <Th>Analysis</Th>
            <Th>Spans</Th>
            <Th>Errors</Th>
            <Th>Duration</Th>
            <Th>Model</Th>
            {view === "mine" ? (
              <>
                <Th>Visibility</Th>
                <Th>Created</Th>
              </>
            ) : (
              <>
                <Th>Contributor</Th>
                <Th>{view === "library" ? "Acquired" : "Listed"}</Th>
              </>
            )}
            {view === "library" && <Th className="w-0" />}
          </tr>
        </thead>
        <tbody>
          {traces.map((trace) => (
            <tr
              key={trace.trace_id}
              className="border-b transition-colors last:border-b-0 hover:bg-accent/50"
            >
              {selection && (
                <td className="px-3 py-2.5">
                  <SelectBox
                    checked={selection.selected.has(trace.trace_id)}
                    onToggle={() => selection.toggle(trace.trace_id)}
                    label={`Select ${trace.name}`}
                  />
                </td>
              )}
              <td className="max-w-72 px-4 py-2.5">
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "size-2 shrink-0 rounded-full",
                      trace.status === "error" ? "bg-error-deep" : "bg-status-ok",
                    )}
                    title={trace.status === "error" ? "Trace contains errors" : "Trace OK"}
                  />
                  <Link
                    href={detailHref(view, trace.trace_id)}
                    className="truncate font-medium hover:underline"
                  >
                    {trace.name}
                  </Link>
                  {view !== "mine" && trace.is_owner && (
                    <VisibilityBadge visibility={trace.visibility} />
                  )}
                  {view !== "library" && view !== "mine" && trace.acquired && <LibraryBadge />}
                  {newIds?.has(trace.trace_id) && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-link-deep">
                      <Sparkles className="size-3" /> new
                    </span>
                  )}
                </span>
                {view !== "mine" && trace.description && (
                  <p className="mt-0.5 truncate pl-4 text-xs text-muted-foreground">
                    {trace.description}
                  </p>
                )}
              </td>
              <td className="px-4 py-2.5">
                <span className="inline-flex items-center gap-2">
                  <TraceOutcome trace={trace} placeholder={view !== "mine"} />
                  {view === "mine" && trace.open_review_item_id !== null && (
                    <NeedsReviewLink itemId={trace.open_review_item_id} />
                  )}
                </span>
              </td>
              <MonoTd>{trace.span_count}</MonoTd>
              <MonoTd className={cn(trace.error_count > 0 && "text-error-deep")}>
                {trace.error_count}
              </MonoTd>
              <MonoTd>{formatDuration(trace.duration_ms)}</MonoTd>
              <MonoTd className="max-w-48 truncate">{trace.model ?? "—"}</MonoTd>
              {view === "mine" ? (
                <>
                  <td className="px-4 py-2.5">
                    <VisibilityBadge visibility={trace.visibility} />
                  </td>
                  <MonoTd>{formatDate(trace.created_at)}</MonoTd>
                </>
              ) : (
                <>
                  <td className="max-w-36 truncate px-4 py-2.5 text-xs text-muted-foreground">
                    {trace.owner_display_name ?? "unknown contributor"}
                  </td>
                  <MonoTd>
                    {view === "library"
                      ? trace.acquired_at
                        ? formatDate(trace.acquired_at)
                        : "—"
                      : trace.listed_at
                        ? formatDate(trace.listed_at)
                        : "—"}
                  </MonoTd>
                </>
              )}
              {view === "library" && (
                <td className="px-3 py-2.5 text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label={`Download ${trace.name}`}
                    onClick={() => onDownload(trace)}
                  >
                    <Download />
                  </Button>
                  {downloadError === trace.trace_id && (
                    <p className="mt-1 text-xs text-error-deep">Download failed.</p>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
