"use client";

import { useEffect, useMemo, useState } from "react";
import type { TraceSpan } from "@evilmartians/agent-prism-types";
import { ListTree, MessageSquare } from "lucide-react";

import { DetailsView } from "@/components/agent-prism/DetailsView/DetailsView";
import { TreeView } from "@/components/agent-prism/TreeView";
import { buildConversation, isContentSpan } from "@/components/traces/conversation";
import { ConversationView } from "@/components/traces/conversation-view";
import { buildSpanTree, defaultExpandedIds, withDetail } from "@/components/traces/span-tree";
import { ApiError } from "@/lib/api/client";
import { getSpan, listAllSpans, type SpanDetail, type SpanListItem } from "@/lib/api/traces";
import { cn } from "@/lib/utils";

type LoadState =
  | { phase: "loading"; spansLoaded: number; spansTotal: number | null }
  | { phase: "error" }
  | { phase: "ready"; spans: SpanListItem[]; roots: TraceSpan[] };

type EvidenceView = "conversation" | "spans";

// Conversation reconstruction needs full attributes, one request per
// llm/tool span — capped so a pathological trace can't issue thousands.
const MAX_CONTENT_SPANS = 200;

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

function ViewToggle({
  view,
  onChange,
}: {
  view: EvidenceView;
  onChange: (view: EvidenceView) => void;
}) {
  const options = [
    { value: "conversation" as const, label: "Conversation", Icon: MessageSquare },
    { value: "spans" as const, label: "Spans", Icon: ListTree },
  ];
  return (
    <div className="inline-flex shrink-0 self-start rounded-md border bg-background p-0.5">
      {options.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors",
            view === value
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="size-3" /> {label}
        </button>
      ))}
    </div>
  );
}

/** The trace inspection core, shared by the trace detail page and the review
 *  resolve view (4_pages.md: the reviewer sees the same inspection
 *  components, on one screen). Defaults to a reconstructed chat-style
 *  conversation; the span tree + details panel sits behind a toggle. Owns
 *  span loading and attribute fetching; the host page owns trace metadata. */
export function TraceEvidence({ traceId, className }: { traceId: string; className?: string }) {
  const [state, setState] = useState<LoadState>({
    phase: "loading",
    spansLoaded: 0,
    spansTotal: null,
  });
  const [view, setView] = useState<EvidenceView>("conversation");
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Map<string, SpanDetail>>(new Map());
  const [convo, setConvo] = useState<{ loaded: number; total: number; done: boolean }>({
    loaded: 0,
    total: 0,
    done: false,
  });

  // Hosts remount per trace (keyed), so state never carries across traces.
  useEffect(() => {
    let cancelled = false;
    listAllSpans(traceId, (loaded, total) => {
      if (!cancelled) {
        setState((prev) =>
          prev.phase === "loading"
            ? { phase: "loading", spansLoaded: loaded, spansTotal: total }
            : prev,
        );
      }
    })
      .then((spans) => {
        if (cancelled) return;
        const roots = buildSpanTree(spans);
        setExpandedIds(defaultExpandedIds(roots));
        setState({ phase: "ready", spans, roots });
      })
      .catch(() => {
        if (!cancelled) setState({ phase: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [traceId]);

  // Prefetch llm/tool span details for the conversation view, one at a time
  // (the per-user rate limit makes parallel fetching counterproductive);
  // 429s back off and retry, other failures skip the span (fail open).
  useEffect(() => {
    if (state.phase !== "ready") return;
    let cancelled = false;
    const content = state.spans.filter(isContentSpan).slice(0, MAX_CONTENT_SPANS);
    setConvo({ loaded: 0, total: content.length, done: content.length === 0 });
    (async () => {
      let loaded = 0;
      for (const span of content) {
        let retries = 0;
        for (;;) {
          if (cancelled) return;
          try {
            const detail = await getSpan(traceId, span.span_id);
            if (cancelled) return;
            setDetails((prev) =>
              prev.has(span.span_id) ? prev : new Map(prev).set(span.span_id, detail),
            );
            break;
          } catch (err) {
            if (err instanceof ApiError && err.status === 429 && retries < 5) {
              retries += 1;
              await new Promise((resolve) => setTimeout(resolve, 1100));
              continue;
            }
            break;
          }
        }
        loaded += 1;
        if (!cancelled) setConvo({ loaded, total: content.length, done: false });
      }
      if (!cancelled) setConvo({ loaded: content.length, total: content.length, done: true });
    })();
    return () => {
      cancelled = true;
    };
  }, [state, traceId]);

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

  const conversation = useMemo(
    () => (state.phase === "ready" ? buildConversation(state.spans, details) : []),
    [state, details],
  );

  if (state.phase === "loading") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="size-3 animate-spin rounded-full border-2 border-border border-t-foreground" />
        {state.spansTotal !== null && state.spansTotal > state.spansLoaded
          ? `Loading spans… ${state.spansLoaded.toLocaleString()} of ${state.spansTotal.toLocaleString()}`
          : "Loading spans…"}
      </p>
    );
  }

  if (state.phase === "error") {
    return <p className="text-sm text-error-deep">Could not load the trace’s spans.</p>;
  }

  const selectedNode = selectedId ? nodeById.get(selectedId) : undefined;
  const selectedDetail = selectedId ? details.get(selectedId) : undefined;
  const panelSpan =
    selectedNode && selectedDetail ? withDetail(selectedNode, selectedDetail) : selectedNode;

  const contentSpanCount = state.spans.filter(isContentSpan).length;

  return (
    <div className={cn("flex h-[calc(100vh-22rem)] min-h-96 flex-col gap-3", className)}>
      <ViewToggle view={view} onChange={setView} />

      {view === "conversation" ? (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border bg-background p-4">
          {conversation.length > 0 && <ConversationView items={conversation} />}
          {!convo.done && (
            <p
              className={cn(
                "flex items-center gap-2 text-sm text-muted-foreground",
                conversation.length > 0 && "mt-4",
              )}
            >
              <span className="size-3 animate-spin rounded-full border-2 border-border border-t-foreground" />
              Reconstructing conversation… {convo.loaded} of {convo.total}
            </p>
          )}
          {convo.done && conversation.length === 0 && (
            <div className="text-sm text-muted-foreground">
              <p>No conversation content could be extracted from this trace.</p>
              <button
                type="button"
                onClick={() => setView("spans")}
                className="mt-2 font-medium text-link hover:underline"
              >
                Inspect the raw spans instead
              </button>
            </div>
          )}
          {convo.done && contentSpanCount > MAX_CONTENT_SPANS && (
            <p className="mt-4 text-xs text-muted-foreground">
              Showing the first {MAX_CONTENT_SPANS} steps — switch to the span view for the full
              trace.
            </p>
          )}
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-5">
          <div className="overflow-y-auto rounded-lg border bg-background py-2 lg:col-span-3">
            <TreeView
              spans={state.roots}
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
      )}
    </div>
  );
}
