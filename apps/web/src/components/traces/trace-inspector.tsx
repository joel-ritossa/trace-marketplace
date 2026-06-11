"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Download } from "lucide-react";
import type { TraceSpan } from "@evilmartians/agent-prism-types";

import { DetailsView } from "@/components/agent-prism/DetailsView/DetailsView";
import { TreeView } from "@/components/agent-prism/TreeView";
import { buildSpanTree, defaultExpandedIds, withDetail } from "@/components/traces/span-tree";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  downloadTrace,
  getSpan,
  getTrace,
  listAllSpans,
  type SpanDetail,
  type TraceDetail,
} from "@/lib/api/traces";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

type LoadState =
  | { phase: "loading"; spansLoaded: number; spansTotal: number | null }
  | { phase: "not-found" }
  | { phase: "error"; message: string }
  | { phase: "ready"; trace: TraceDetail; roots: TraceSpan[] };

function flatten(roots: TraceSpan[]): Map<string, TraceSpan> {
  const map = new Map<string, TraceSpan>();
  const stack = [...roots];
  while (stack.length > 0) {
    const node = stack.pop()!;
    map.set(node.id, node);
    stack.push(...(node.children ?? []));
  }
  return map;
}

export function TraceInspector({ traceId }: { traceId: string }) {
  const [state, setState] = useState<LoadState>({
    phase: "loading",
    spansLoaded: 0,
    spansTotal: null,
  });
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Map<string, SpanDetail>>(new Map());
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getTrace(traceId),
      listAllSpans(traceId, (loaded, total) => {
        if (!cancelled) {
          setState((prev) =>
            prev.phase === "loading" ? { phase: "loading", spansLoaded: loaded, spansTotal: total } : prev,
          );
        }
      }),
    ])
      .then(([trace, spans]) => {
        if (cancelled) return;
        const roots = buildSpanTree(spans);
        setExpandedIds(defaultExpandedIds(roots));
        setState({ phase: "ready", trace, roots });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ phase: "not-found" });
        } else {
          setState({
            phase: "error",
            message: err instanceof ApiError ? err.message : "Could not load the trace.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [traceId]);

  // Fetch full attributes/events lazily, when a span is first selected.
  async function onSpanSelect(span: TraceSpan) {
    setSelectedId(span.id);
    if (details.has(span.id)) return;
    try {
      const detail = await getSpan(traceId, span.id);
      setDetails((prev) => new Map(prev).set(span.id, detail));
    } catch {
      // Panel falls back to the light fields; reselecting retries.
    }
  }

  const nodeById = useMemo(
    () => (state.phase === "ready" ? flatten(state.roots) : new Map<string, TraceSpan>()),
    [state],
  );

  if (state.phase === "loading") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="size-3 animate-spin rounded-full border-2 border-border border-t-foreground" />
        {state.spansTotal !== null && state.spansTotal > state.spansLoaded
          ? `Loading spans… ${state.spansLoaded.toLocaleString()} of ${state.spansTotal.toLocaleString()}`
          : "Loading trace…"}
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

  const { trace, roots } = state;
  const selectedNode = selectedId ? nodeById.get(selectedId) : undefined;
  const selectedDetail = selectedId ? details.get(selectedId) : undefined;
  const panelSpan =
    selectedNode && selectedDetail ? withDetail(selectedNode, selectedDetail) : selectedNode;

  async function onDownload() {
    setDownloading(true);
    setDownloadError(false);
    try {
      await downloadTrace(trace.trace_id, `${trace.name.replaceAll("/", "_")}.json`);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloading(false);
    }
  }

  const meta: [string, string][] = [
    ["Duration", formatDuration(trace.duration_ms)],
    ["Spans", String(trace.span_count)],
    ["Errors", String(trace.error_count)],
    ["Provider", trace.provider ?? "—"],
    ["Model", trace.model ?? "—"],
    ["Service", trace.service_name ?? "—"],
    ["Tools", trace.tool_names.length > 0 ? trace.tool_names.join(", ") : "—"],
    ["Source", `${trace.source_format} · importer ${trace.importer_version}`],
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/traces"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3" /> Traces
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2.5 text-2xl font-semibold tracking-tight">
              <span
                className={cn(
                  "size-2.5 shrink-0 rounded-full",
                  trace.status === "error" ? "bg-error-deep" : "bg-status-ok",
                )}
                title={trace.status === "error" ? "Trace contains errors" : "Trace OK"}
              />
              <span className="truncate">{trace.name}</span>
            </h1>
            {trace.error_types.length > 0 && (
              <p className="mt-1 text-sm text-error-deep">
                Error types: {trace.error_types.join(", ")}
              </p>
            )}
          </div>
          {trace.can_download && (
            <div className="flex flex-col items-end gap-1">
              <Button size="sm" variant="outline" disabled={downloading} onClick={onDownload}>
                <Download /> Download raw
              </Button>
              {downloadError && (
                <p className="text-xs text-error-deep">Download failed — try again.</p>
              )}
            </div>
          )}
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border bg-background px-4 py-3 text-sm sm:grid-cols-4">
          {meta.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="truncate font-mono text-xs" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="grid h-[calc(100vh-22rem)] min-h-96 grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="overflow-y-auto rounded-lg border bg-background py-2 lg:col-span-3">
          <TreeView
            spans={roots}
            selectedSpan={panelSpan}
            onSpanSelect={onSpanSelect}
            expandedSpansIds={expandedIds}
            onExpandSpansIdsChange={setExpandedIds}
            spanCardViewOptions={{ expandButton: "inside" }}
          />
        </div>
        <div className="overflow-y-auto rounded-lg border bg-background lg:col-span-2">
          {panelSpan ? (
            <DetailsView key={panelSpan.id} data={panelSpan} className="border-0" />
          ) : (
            <p className="p-4 text-sm text-muted-foreground">
              Select a span to inspect its attributes and events.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
