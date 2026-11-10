"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ChevronDown } from "lucide-react";

import { AnalysisSection } from "@/components/traces/analysis-section";
import { TraceOutcome, VisibilityBadge } from "@/components/traces/badges";
import { TraceHeaderActions, TraceMetaEditor } from "@/components/traces/trace-actions";
import { TraceEvidence, type SpanFocus } from "@/components/traces/trace-evidence";
import { useTraceDetail } from "@/components/traces/use-trace-detail";
import { Button } from "@/components/ui/button";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

export function TraceInspector({ traceId, focusTurn }: { traceId: string; focusTurn?: number }) {
  const { state, setTrace } = useTraceDetail(traceId);
  const [overviewOpen, setOverviewOpen] = useState(true);
  const [spanFocus, setSpanFocus] = useState<SpanFocus | null>(null);

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
            <TraceOutcome
              outcome={trace.analysis.session.outcome}
              status={trace.analysis.session.status}
              failed={trace.analysis.failed_reason !== null}
            />
          </h1>
          <TraceHeaderActions trace={trace} onChange={setTrace} />
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
                <TraceMetaEditor trace={trace} onChange={setTrace} />
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
            <AnalysisSection
              trace={trace}
              onChange={setTrace}
              onShowSpan={(sourceSpanId) =>
                setSpanFocus((prev) => ({ sourceSpanId, seq: (prev?.seq ?? 0) + 1 }))
              }
              focusTurn={focusTurn}
            />
          </div>
        )}
      </section>

      <TraceEvidence key={trace.trace_id} traceId={trace.trace_id} focus={spanFocus} />
    </div>
  );
}
