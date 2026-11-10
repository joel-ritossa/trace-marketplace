"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, Sparkles } from "lucide-react";
import {
  AgentBadge,
  LibraryBadge,
  NeedsReviewLink,
  VisibilityBadge,
} from "@/components/traces/badges";
import {
  LabelSummary,
  TraceOutcomeControl,
  useLazySource,
  type SkillFilter,
} from "@/components/traces/label-popovers";
import { SelectBox } from "@/components/traces/bulk-bar";
import { Button } from "@/components/ui/button";
import { downloadTrace, type TraceListItem } from "@/lib/api/traces";
import { agentOf, cleanName, traceTitle } from "@/components/traces/names";
import { formatDate, formatDuration, formatShortDate } from "@/lib/format";
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

/** The Analysis cell's controls: outcome (or status), then the label pills;
 *  each opens the shared popovers, fetching the trace on first open. */
function RowAnalysis({
  trace,
  skillFilter,
}: {
  trace: TraceListItem;
  skillFilter?: SkillFilter;
}) {
  const source = useLazySource(trace.trace_id);
  return (
    <>
      <TraceOutcomeControl
        outcome={trace.outcome}
        status={trace.analysis_status}
        failed={trace.analysis_failed}
        source={source}
      />
      <LabelSummary
        traceId={trace.trace_id}
        taskCategories={trace.task_categories}
        failureModes={trace.failure_modes}
        skillNames={trace.skill_names}
        skillFilter={skillFilter}
      />
    </>
  );
}

/** Date and time where the table has room; the day alone below xl. */
function RowDate({ iso }: { iso: string }) {
  return (
    <span title={formatDate(iso)}>
      <span className="hidden xl:inline">{formatDate(iso)}</span>
      <span className="xl:hidden">{formatShortDate(iso)}</span>
    </span>
  );
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cn("px-4 py-2.5 font-medium", className)}>{children}</th>;
}

function MonoTd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <td
      className={cn(
        "whitespace-nowrap px-4 py-2.5 font-mono text-xs text-muted-foreground",
        className,
      )}
    >
      {children}
    </td>
  );
}

// Low-value columns drop as the table narrows, so name and analysis keep room.
const WIDE_ONLY = "hidden xl:table-cell";
const WIDEST_ONLY = "hidden 2xl:table-cell";

/** The unified trace list (4_pages.md): one dense row spec for every list
 *  surface — my traces, marketplace, library, subscription feeds — with
 *  scope-driven columns and actions. */
export function TraceList({
  traces,
  view,
  selection,
  newIds,
  skillFilter,
}: {
  traces: TraceListItem[];
  view: TraceListView;
  selection?: Selection;
  newIds?: ReadonlySet<string>;
  // Lets a row's skills popover add to the list's filters.
  skillFilter?: SkillFilter;
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
            <Th className="min-w-40 xl:min-w-64">Name</Th>
            <Th className="min-w-48">Analysis</Th>
            <Th className={WIDE_ONLY}>Turns</Th>
            <Th className={WIDEST_ONLY}>Spans</Th>
            <Th className={WIDE_ONLY}>Errors</Th>
            <Th>Duration</Th>
            <Th className={WIDEST_ONLY}>Model</Th>
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
              <td className="max-w-60 px-4 py-2.5 xl:max-w-96">
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "size-2 shrink-0 rounded-full",
                      trace.status === "error" ? "bg-error-deep" : "bg-status-ok",
                    )}
                    title={
                      trace.error_count > 0
                        ? `${trace.error_count} span error${trace.error_count === 1 ? "" : "s"}`
                        : "No span errors"
                    }
                  />
                  <Link
                    href={detailHref(view, trace.trace_id)}
                    title={[
                      `First ask: ${cleanName(trace.name)}`,
                      view !== "mine" && trace.description,
                    ]
                      .filter(Boolean)
                      .join("\n")}
                    className="truncate font-medium hover:underline"
                  >
                    {traceTitle(trace.name, trace.goal)}
                  </Link>
                  {/* One row layout on every list surface: title, then badges. */}
                  {agentOf(trace.name) && <AgentBadge agent={agentOf(trace.name)!} />}
                  {view !== "mine" && trace.is_owner && (
                    <VisibilityBadge visibility={trace.visibility} />
                  )}
                  {view !== "mine" && view !== "library" && trace.acquired && <LibraryBadge />}
                  {newIds?.has(trace.trace_id) && (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-link-deep">
                      <Sparkles className="size-3" /> new
                    </span>
                  )}
                </span>
              </td>
              <td className="px-4 py-2.5">
                <span className="flex max-w-56 min-w-0 items-center gap-1.5 overflow-hidden xl:max-w-72">
                  <RowAnalysis trace={trace} skillFilter={skillFilter} />
                  {view === "mine" && trace.has_open_review_item && (
                    <NeedsReviewLink traceId={trace.trace_id} />
                  )}
                </span>
              </td>
              <MonoTd className={WIDE_ONLY}>{trace.turn_count}</MonoTd>
              <MonoTd className={WIDEST_ONLY}>{trace.span_count}</MonoTd>
              <MonoTd className={cn(WIDE_ONLY, trace.error_count > 0 && "text-error-deep")}>
                {trace.error_count}
              </MonoTd>
              <MonoTd>{formatDuration(trace.duration_ms)}</MonoTd>
              <MonoTd className={cn(WIDEST_ONLY, "max-w-48 truncate")}>{trace.model ?? "—"}</MonoTd>
              {view === "mine" ? (
                <>
                  <td className="px-4 py-2.5">
                    <VisibilityBadge visibility={trace.visibility} />
                  </td>
                  <MonoTd>
                    <RowDate iso={trace.created_at} />
                  </MonoTd>
                </>
              ) : (
                <>
                  <td className="max-w-36 truncate px-4 py-2.5 text-xs text-muted-foreground">
                    {trace.owner_display_name ?? "unknown contributor"}
                  </td>
                  <MonoTd>
                    {(() => {
                      const at = view === "library" ? trace.acquired_at : trace.listed_at;
                      return at ? <RowDate iso={at} /> : "—";
                    })()}
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
