"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronDown } from "lucide-react";

import { AnalysisSection } from "@/components/traces/analysis-section";
import { TraceOutcome, VisibilityBadge } from "@/components/traces/badges";
import { TraceHeaderActions, TraceMetaEditor } from "@/components/traces/trace-actions";
import { TraceEvidence } from "@/components/traces/trace-evidence";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { getTrace, type TraceDetail } from "@/lib/api/traces";
import { formatDuration } from "@/lib/format";
import { useRealtimeRefetch } from "@/lib/realtime";
import { cn } from "@/lib/utils";

type LoadState =
  | { phase: "loading" }
  | { phase: "not-found" }
  | { phase: "error"; message: string }
  | { phase: "ready"; trace: TraceDetail };

export function TraceInspector({ traceId }: { traceId: string }) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [overviewOpen, setOverviewOpen] = useState(true);
  const loadTicket = useRef(0);

  const load = useCallback(async () => {
    const ticket = ++loadTicket.current;
    try {
      const trace = await getTrace(traceId);
      if (ticket === loadTicket.current) setState({ phase: "ready", trace });
    } catch (err) {
      if (ticket !== loadTicket.current) return;
      if (err instanceof ApiError && err.status === 404) {
        setState({ phase: "not-found" });
      } else {
        // A failed background refetch must not blank a rendered trace.
        setState((prev) =>
          prev.phase === "ready"
            ? prev
            : {
                phase: "error",
                message: err instanceof ApiError ? err.message : "Could not load the trace.",
              },
        );
      }
    }
  }, [traceId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Live invalidation: metadata/visibility edits land via "traces", an
  // analysis verdict (header outcome badge) via "trace_analysis".
  useRealtimeRefetch("traces", load);
  useRealtimeRefetch("trace_analysis", load);

  if (state.phase === "loading") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="size-3 animate-spin rounded-full border-2 border-border border-t-foreground" />
        Loading trace…
      </p>
    );
  }

  if (state.phase === "not-found") {
    return (
      <div>
        <p className="text-sm font-medium">Trace not found</p>
        <p className="mt-1 text-sm text-muted-foreground">
          It may have been removed, or the link is wrong.
        </p>
        <Button asChild size="sm" variant="outline" className="mt-4">
          <Link href="/traces">
            <ArrowLeft /> Back to traces
          </Link>
        </Button>
      </div>
    );
  }

  if (state.phase === "error") {
    return <p className="text-sm text-error-deep">{state.message}</p>;
  }

  const { trace } = state;

  function onTraceChange(updated: TraceDetail) {
    setState((prev) => (prev.phase === "ready" ? { ...prev, trace: updated } : prev));
  }

  const meta: [string, string][] = [
    ["Duration", formatDuration(trace.duration_ms)],
    ["Spans", String(trace.span_count)],
    ["Errors", String(trace.error_count)],
    ["Tokens", trace.total_tokens !== null ? trace.total_tokens.toLocaleString() : "—"],
    ["Provider", trace.provider ?? "—"],
    ["Model", trace.model ?? "—"],
    ["Service", trace.service_name ?? "—"],
    ["Tools", trace.tool_names.length > 0 ? trace.tool_names.join(", ") : "—"],
    ["Contributor", trace.owner_display_name ?? "—"],
    ["Source", `${trace.source_format} · importer ${trace.importer_version}`],
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* Header strip (4_pages.md trace-detail layout): identity + the one
          actions cluster, sticky under the top bar. */}
      <div className="sticky top-14 z-10 -mx-6 -mt-8 border-b bg-canvas-soft/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <h1 className="flex min-w-0 items-center gap-2.5 text-lg font-semibold tracking-tight">
            <span
              className={cn(
                "size-2.5 shrink-0 rounded-full",
                trace.status === "error" ? "bg-error-deep" : "bg-status-ok",
              )}
              title={trace.status === "error" ? "Trace contains errors" : "Trace OK"}
            />
            <span className="truncate">{trace.name}</span>
            <VisibilityBadge visibility={trace.visibility} />
            <TraceOutcome trace={trace} />
          </h1>
          <TraceHeaderActions trace={trace} onChange={onTraceChange} />
        </div>
      </div>

      {/* Overview region: metadata + analysis, collapsible so the evidence
          can take the screen. */}
      <section>
        <button
          type="button"
          onClick={() => setOverviewOpen((open) => !open)}
          className="flex items-center gap-1.5 text-sm font-semibold transition-colors hover:text-muted-foreground"
          aria-expanded={overviewOpen}
        >
          <ChevronDown
            className={cn("size-4 transition-transform", !overviewOpen && "-rotate-90")}
          />
          Overview
        </button>
        {overviewOpen && (
          <div className="mt-3 grid items-start gap-4 xl:grid-cols-2">
            <div className="flex flex-col gap-4">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border bg-background px-4 py-3 text-sm sm:grid-cols-3">
                {meta.map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-xs text-muted-foreground">{label}</dt>
                    <dd className="truncate font-mono text-xs" title={value}>
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
              {trace.error_types.length > 0 && (
                <p className="text-sm text-error-deep">
                  Error types: {trace.error_types.join(", ")}
                </p>
              )}
              {trace.is_owner ? (
                <TraceMetaEditor trace={trace} onChange={onTraceChange} />
              ) : (
                <>
                  {trace.description && (
                    <p className="max-w-2xl text-sm text-muted-foreground">{trace.description}</p>
                  )}
                  {trace.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {trace.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            <AnalysisSection traceId={trace.trace_id} isOwner={trace.is_owner} />
          </div>
        )}
      </section>

      <TraceEvidence key={trace.trace_id} traceId={trace.trace_id} />
    </div>
  );
}
