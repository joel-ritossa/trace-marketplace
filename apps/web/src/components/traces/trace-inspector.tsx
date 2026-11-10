"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ChevronDown } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { AnalysisSection, loadedSource, type Nav } from "@/components/traces/analysis-section";
import { AgentBadge, VisibilityBadge } from "@/components/traces/badges";
import { TraceOutcomeControl } from "@/components/traces/label-popovers";
import { agentOf, cleanName, traceTitle } from "@/components/traces/names";
import { traceSpanPanel } from "@/components/traces/span-panels";
import { TraceHeaderActions, TraceMetaEditor } from "@/components/traces/trace-actions";
import {
  TraceEvidence,
  type EvidenceView,
  type SpanFocus,
} from "@/components/traces/trace-evidence";
import { useTraceDetail } from "@/components/traces/use-trace-detail";
import { Button } from "@/components/ui/button";
import { ExpandableText } from "@/components/ui/expandable-text";
import { listAgents, type AgentSpawn, type TraceAnalysis } from "@/lib/api/traces";
import { formatCompact, formatDuration } from "@/lib/format";
import { useMinWidth } from "@/lib/use-media";
import { cn } from "@/lib/utils";

// The analysis/evidence region fills the viewport under the top bar and the
// sticky header strip (title + actions rows), so each panel scrolls itself.
const REGION_HEIGHT = "h-[calc(100vh-12.5rem)] min-h-[28rem]";

export function TraceInspector({
  traceId,
  focusTurn,
  focusSpan,
  focusAgent,
  initialView,
}: {
  traceId: string;
  focusTurn?: number;
  focusSpan?: string;
  focusAgent?: string;
  initialView?: EvidenceView;
}) {
  const { state, setTrace } = useTraceDetail(traceId);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Subagent spawns, fetched once the detail says there are any.
  const [agents, setAgents] = useState<AgentSpawn[] | null>(null);
  const subagentCount = state.phase === "ready" ? (state.trace.subagents?.count ?? 0) : 0;
  useEffect(() => {
    if (subagentCount === 0) return;
    let cancelled = false;
    listAgents(traceId)
      .then((list) => !cancelled && setAgents(list))
      .catch(() => !cancelled && setAgents([]));
    return () => {
      cancelled = true;
    };
  }, [traceId, subagentCount]);
  // ?agent=<spawn span id> scopes the evidence pane; ?view= picks its view.
  const [agentScope, setAgentScopeState] = useState<string | null>(focusAgent ?? null);
  const [viewRequest, setViewRequest] = useState<{
    view: EvidenceView;
    turn?: number;
    seq: number;
  } | null>(null);
  const setParam = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (value === null) params.delete(key);
    else params.set(key, value);
    router.replace(params.size > 0 ? `${pathname}?${params}` : pathname, { scroll: false });
  };
  const setAgentScope = (spanId: string | null) => {
    setAgentScopeState(spanId);
    setParam("agent", spanId);
    setPane("evidence");
  };
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [spanFocus, setSpanFocus] = useState<SpanFocus | null>(
    focusSpan ? { sourceSpanId: focusSpan, seq: 1 } : null,
  );
  const [turnRequest, setTurnRequest] = useState<{ turnIndex: number; seq: number } | null>(
    null,
  );
  // Analysis and evidence side by side when wide; tabs below xl.
  const wide = useMinWidth(1280);
  // Narrow layouts open on the evidence when a span (and no turn) is asked for.
  const [pane, setPane] = useState<"analysis" | "evidence">(
    (focusSpan || focusAgent || initialView) && focusTurn === undefined ? "evidence" : "analysis",
  );

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

  const nav: Nav = {
    goToTurn: (turnIndex) => {
      setTurnRequest((prev) => ({ turnIndex, seq: (prev?.seq ?? 0) + 1 }));
      setPane("analysis");
    },
    showSpan: (sourceSpanId) => {
      setSpanFocus((prev) => ({ sourceSpanId, seq: (prev?.seq ?? 0) + 1 }));
      setPane("evidence");
    },
    showAgents: (turn) => {
      setViewRequest((prev) => ({ view: "agents", turn, seq: (prev?.seq ?? 0) + 1 }));
      setPane("evidence");
    },
    openAgent: (spanId) => setAgentScope(spanId),
  };
  const onAnalysisChange = (analysis: TraceAnalysis) => setTrace({ ...trace, analysis });
  const title = traceTitle(trace.name, trace.analysis.session.goal);
  const agent = agentOf(trace.name, trace.source_format);

  const meta: [string, string, string?][] = [
    ["Duration", formatDuration(trace.duration_ms)],
    ["Spans", trace.span_count.toLocaleString()],
    ["Errors", trace.error_count.toLocaleString()],
    [
      // Session logs count cached input on every request.
      "Tokens (incl. cached)",
      trace.total_tokens !== null ? formatCompact(trace.total_tokens) : "—",
      trace.total_tokens?.toLocaleString(),
    ],
    ["Provider", trace.provider ?? "—"],
    ["Model", trace.model ?? "—"],
    ["Service", trace.service_name ?? "—"],
    ["Tools", trace.tool_names.length > 0 ? trace.tool_names.join(", ") : "—"],
    ["Skills", trace.skill_names?.length ? trace.skill_names.join(", ") : "—"],
    ["Contributor", trace.owner_display_name ?? "—"],
    ["Source", `${trace.source_format} · importer ${trace.importer_version}`],
  ];

  const analysis = (
    <AnalysisSection
      trace={trace}
      onChange={setTrace}
      onShowSpan={nav.showSpan}
      focusTurn={focusTurn}
      turnRequest={turnRequest}
      syncUrl
      className={cn(wide && "h-full overflow-y-auto")}
      agents={agents}
      showAgents={subagentCount > 0 ? nav.showAgents : undefined}
      openAgent={nav.openAgent}
      scoped={agentScope !== null}
    />
  );
  const evidence = (
    <TraceEvidence
      key={trace.trace_id}
      traceId={trace.trace_id}
      focus={spanFocus}
      split={wide ? "vertical" : "horizontal"}
      className={wide ? "h-full min-h-0" : REGION_HEIGHT}
      renderSpanPanel={(ctx) => traceSpanPanel(ctx, trace, nav, onAnalysisChange, agents)}
      agents={subagentCount > 0 ? agents : undefined}
      agentScope={agentScope}
      onScope={setAgentScope}
      initialView={initialView}
      viewRequest={viewRequest}
      onViewChange={(view) => setParam("view", view === "conversation" ? null : view)}
    />
  );

  return (
    <div className="flex flex-col gap-4">
      {/* Header strip (4_pages.md trace-detail layout), sticky under the top
          bar: a fixed title row, then the actions row. */}
      <div className="sticky top-14 z-10 -mx-6 -mt-8 flex flex-col gap-2 border-b bg-canvas-soft/95 px-6 py-3 backdrop-blur">
        <h1 className="flex min-w-0 items-center gap-2.5 text-lg font-semibold tracking-tight">
          <span
            className={cn(
              "size-2.5 shrink-0 rounded-full",
              trace.status === "error" ? "bg-error-deep" : "bg-status-ok",
            )}
            title={trace.status === "error" ? "Trace contains errors" : "Trace OK"}
          />
          <span className="min-w-0 truncate" title={`First ask: ${cleanName(trace.name)}`}>
            {title}
          </span>
          {agent && <AgentBadge agent={agent} />}
          <VisibilityBadge visibility={trace.visibility} />
          <TraceOutcomeControl
            source={loadedSource(trace, nav)}
            outcome={trace.analysis.session.outcome}
            status={trace.analysis.session.status}
            failed={trace.analysis.failed_reason !== null}
          />
        </h1>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              aria-expanded={detailsOpen}
              onClick={() => setDetailsOpen((open) => !open)}
            >
              <ChevronDown className={cn("transition-transform", !detailsOpen && "-rotate-90")} />
              Details
            </Button>
            {!wide && (
              <>
                <Button
                  size="sm"
                  variant={pane === "analysis" ? "secondary" : "ghost"}
                  aria-pressed={pane === "analysis"}
                  onClick={() => setPane("analysis")}
                >
                  Analysis
                </Button>
                <Button
                  size="sm"
                  variant={pane === "evidence" ? "secondary" : "ghost"}
                  aria-pressed={pane === "evidence"}
                  onClick={() => setPane("evidence")}
                >
                  Evidence
                </Button>
              </>
            )}
          </div>
          <TraceHeaderActions trace={trace} onChange={setTrace} />
        </div>
      </div>

      {detailsOpen && (
        <div className="grid items-start gap-4 lg:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-2">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border bg-background px-4 py-3 text-sm sm:grid-cols-3">
              {meta.map(([label, value, exact]) => (
                <div key={label} className="min-w-0">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="font-mono text-xs" title={exact}>
                    <ExpandableText text={value} lines={1} />
                  </dd>
                </div>
              ))}
            </dl>
            {trace.error_types.length > 0 && (
              <p className="text-sm text-error-deep">Error types: {trace.error_types.join(", ")}</p>
            )}
          </div>
          {trace.is_owner ? (
            <TraceMetaEditor trace={trace} onChange={setTrace} />
          ) : (
            <div className="flex min-w-0 flex-col gap-2">
              {trace.description && (
                <p className="max-w-2xl text-sm text-muted-foreground">{trace.description}</p>
              )}
              {trace.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {trace.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-secondary px-2 py-0.5 text-xs text-foreground/75"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* PanelGroup sizes itself to 100% of its parent, which sets the height. */}
      {wide ? (
        <div className={REGION_HEIGHT}>
        <PanelGroup direction="horizontal" autoSaveId="trace-page">
          <Panel id="analysis" order={1} defaultSize={42} minSize={28}>
            {analysis}
          </Panel>
          <PanelResizeHandle className="group flex w-4 items-center justify-center outline-none">
            <span className="h-8 w-1 rounded-full bg-border transition-colors group-hover:bg-muted-foreground group-focus-visible:bg-muted-foreground group-data-[resize-handle-state=drag]:bg-muted-foreground" />
          </PanelResizeHandle>
          <Panel id="evidence" order={2} defaultSize={58} minSize={30}>
            {evidence}
          </Panel>
        </PanelGroup>
        </div>
      ) : (
        <>
          {/* Both stay mounted so switching keeps loaded spans and state. */}
          <div className={cn(pane !== "analysis" && "hidden")}>{analysis}</div>
          <div className={cn(pane !== "evidence" && "hidden")}>{evidence}</div>
        </>
      )}
    </div>
  );
}
