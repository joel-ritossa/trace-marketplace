"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { TraceSpan } from "@evilmartians/agent-prism-types";
import { ListTree, MessageSquare } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { DetailsView } from "@/components/agent-prism/DetailsView/DetailsView";
import { TreeView } from "@/components/agent-prism/TreeView";
import {
  buildConversation,
  isContentSpan,
  type ConversationItem,
} from "@/components/traces/conversation";
import { ConversationView } from "@/components/traces/conversation-view";
import {
  AgentsView,
  SubagentCard,
  SubagentIcon,
  type TurnInfo,
} from "@/components/traces/agents-view";
import { cleanSpanName } from "@/components/traces/names";
import { ancestorIds, buildSpanTree, spawnBrief, withDetail } from "@/components/traces/span-tree";
import { ApiError } from "@/lib/api/client";
import {
  getSpan,
  listAllSpans,
  type AgentSpawn,
  type SpanDetail,
  type SpanListItem,
} from "@/lib/api/traces";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type LoadState =
  | { phase: "loading"; spansLoaded: number; spansTotal: number | null }
  | { phase: "error" }
  | { phase: "ready"; spans: SpanListItem[]; roots: TraceSpan[] };

export type EvidenceView = "conversation" | "spans" | "agents";

/** A request to reveal one span (a label's evidence), by source span id;
 *  `seq` makes repeat clicks on the same span re-reveal it. */
export type SpanFocus = { sourceSpanId: string; seq: number };

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
  agentCount,
}: {
  view: EvidenceView;
  onChange: (view: EvidenceView) => void;
  agentCount: number;
}) {
  const options: { value: EvidenceView; label: string; Icon: typeof ListTree }[] = [
    { value: "conversation", label: "Conversation", Icon: MessageSquare },
    { value: "spans", label: "Spans", Icon: ListTree },
    ...(agentCount > 0
      ? [{ value: "agents" as const, label: `Agents · ${agentCount}`, Icon: SubagentIcon }]
      : []),
  ];
  return (
    <div className="inline-flex shrink-0 self-start rounded-md border bg-background p-0.5">
      {options.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
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

/** Span tree and detail panel, resizable (the agent-prism viewer's panel
 *  primitive; sizes persist per browser and direction). Side by side when the
 *  evidence has the full width, stacked when it shares the row. */
function SpanPanels({
  direction,
  tree,
  detail,
}: {
  direction: "horizontal" | "vertical";
  tree: ReactNode;
  detail: ReactNode;
}) {
  const horizontal = direction === "horizontal";
  return (
    <PanelGroup
      direction={direction}
      autoSaveId={`trace-evidence-spans-${direction}`}
      className="min-h-0 flex-1"
    >
      <Panel id="span-tree" order={1} defaultSize={horizontal ? 60 : 55} minSize={25}>
        {tree}
      </Panel>
      <PanelResizeHandle
        className={cn(
          "group flex items-center justify-center outline-none",
          horizontal ? "w-4" : "h-4",
        )}
      >
        <span
          className={cn(
            "rounded-full bg-border transition-colors group-hover:bg-muted-foreground group-focus-visible:bg-muted-foreground group-data-[resize-handle-state=drag]:bg-muted-foreground",
            horizontal ? "h-8 w-1" : "h-1 w-8",
          )}
        />
      </PanelResizeHandle>
      <Panel id="span-detail" order={2} defaultSize={horizontal ? 40 : 45} minSize={20}>
        {detail}
      </Panel>
    </PanelGroup>
  );
}

/** What a host can show for a span instead of the generic detail panel
 *  (the trace page: a turn's ask, reply and analysis; the session card). */
export type SpanPanelContext = {
  node: TraceSpan;
  sourceSpanId: string | null;
  attributes: Record<string, unknown> | null;
  // The agent's last reply under this span: undefined while loading, null
  // when there is none.
  finalReply: string | null | undefined;
};

const lastAssistantText = (items: ConversationItem[]): string | null => {
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    if (item.kind === "message" && item.role === "assistant") return item.text;
  }
  return null;
};

function lastLlmDescendant(node: TraceSpan): TraceSpan | undefined {
  let last: TraceSpan | undefined;
  const stack = [...(node.children ?? [])];
  while (stack.length > 0) {
    const n = stack.pop()!;
    if (n.type === "llm_call" && (!last || n.startTime > last.startTime)) last = n;
    stack.push(...(n.children ?? []));
  }
  return last;
}

/** The trace inspection core, shared by the trace detail page and the
 *  similar-trace preview. Defaults to a reconstructed chat-style
 *  conversation; the span tree + details panel sits behind a toggle. Owns
 *  span loading and attribute fetching; the host page owns trace metadata.
 *  `focus` reveals a span: switches to the tree, expands its ancestors (the
 *  tree starts collapsed), selects it and scrolls it into view. */
export function TraceEvidence({
  traceId,
  className,
  focus,
  split = "horizontal",
  renderSpanPanel,
  agents,
  agentScope = null,
  onScope,
  onShowSpan,
  view: controlledView,
  onViewChange,
  agentFocus = null,
  turnFocus = null,
  onTurnSelect,
  onShowAgents,
  rootTitle,
}: {
  traceId: string;
  className?: string;
  focus?: SpanFocus | null;
  split?: "horizontal" | "vertical";
  renderSpanPanel?: (ctx: SpanPanelContext) => ReactNode | null;
  // Subagent spawns (null while loading, absent when the host has none).
  agents?: AgentSpawn[] | null;
  // The subagent (spawn span's source id) the pane is scoped to.
  agentScope?: string | null;
  onScope?: (spanId: string | null) => void;
  // Reveal a span cited by a subagent verdict (the host navigates).
  onShowSpan?: (spanId: string) => void;
  // Controlled by the host (the trace page keeps it in the URL); internal
  // state otherwise (the similar-trace preview).
  view?: EvidenceView;
  onViewChange?: (view: EvidenceView) => void;
  // Scroll the Agents view to a turn's group; seq re-fires.
  agentFocus?: { turn: number; seq: number } | null;
  // The selected turn: scroll the conversation to its start, or select its
  // span in the tree. seq re-fires; only explicit selections send one.
  turnFocus?: { turn: number; seq: number } | null;
  // A turn span was selected here.
  onTurnSelect?: (turnIndex: number) => void;
  // Leave the scope for the Agents view at a turn's group.
  onShowAgents?: (turnIndex: number) => void;
  // The trace's display name for the root row (one name everywhere).
  rootTitle?: string;
}) {
  const [state, setState] = useState<LoadState>({
    phase: "loading",
    spansLoaded: 0,
    spansTotal: null,
  });
  const [ownView, setOwnView] = useState<EvidenceView>("conversation");
  const view = controlledView ?? ownView;
  const setView = (next: EvidenceView) => {
    if (controlledView === undefined) setOwnView(next);
    onViewChange?.(next);
  };
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Map<string, SpanDetail>>(new Map());
  const [convo, setConvo] = useState<{ loaded: number; total: number; done: boolean }>({
    loaded: 0,
    total: 0,
    done: false,
  });
  const treeRef = useRef<HTMLDivElement>(null);
  const [scrollSeq, setScrollSeq] = useState(0);
  // The generic span data instead of the host's panel for the selection.
  const [showRaw, setShowRaw] = useState(false);
  const handledFocus = useRef(0);

  const [reloadKey, setReloadKey] = useState(0);
  // Hosts remount per trace (keyed), so state never carries across traces.
  useEffect(() => {
    let cancelled = false;
    setState({ phase: "loading", spansLoaded: 0, spansTotal: null });
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
        // Open to the turn level: a lone root shows its children.
        setExpandedIds(roots.length === 1 ? [roots[0].id] : []);
        setState({ phase: "ready", spans, roots });
      })
      .catch(() => {
        if (!cancelled) setState({ phase: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [traceId, reloadKey]);

  // Scope: the spawn span's subtree (by tree node id), or the whole trace.
  const scopeNodeId =
    state.phase === "ready" && agentScope
      ? state.spans.find((sp) => sp.source_span_id === agentScope)?.span_id
      : undefined;
  const scopeIds = useMemo(() => {
    if (state.phase !== "ready" || !scopeNodeId) return null;
    const root = flatten(state.roots).get(scopeNodeId);
    return root ? new Set(flatten([root]).keys()) : null;
  }, [state, scopeNodeId]);
  const scopedSpans = useMemo(
    () =>
      state.phase !== "ready"
        ? []
        : scopeIds
          ? state.spans.filter((sp) => scopeIds.has(sp.span_id))
          : state.spans,
    [state, scopeIds],
  );
  const fetched = useRef(new Set<string>());
  const prefetchTurn = turnFocus?.turn;
  // Every span's turn (by tree node id), from the turn spans' subtrees.
  const { turnNodes, turnOfNode } = useMemo(() => {
    const turnNodes = new Map<number, string>();
    const turnOfNode = new Map<string, number>();
    if (state.phase !== "ready") return { turnNodes, turnOfNode };
    for (const node of flatten(state.roots).values()) {
      const m = /^turn (\d+)\b/i.exec(node.title);
      if (!m || node.type !== "agent_invocation") continue;
      const turn = Number(m[1]) - 1;
      turnNodes.set(turn, node.id);
      for (const id of flatten([node]).keys()) turnOfNode.set(id, turn);
    }
    return { turnNodes, turnOfNode };
  }, [state]);

  // Prefetch llm/tool span details for the conversation view, one at a time
  // (the per-user rate limit makes parallel fetching counterproductive);
  // 429s back off and retry, other failures skip the span (fail open).
  useEffect(() => {
    if (state.phase !== "ready") return;
    let cancelled = false;
    // Only while the conversation is on screen: keeps page load to a few
    // requests (and under the rate limit) when another view is open.
    if (view !== "conversation") return;
    // The selected turn's steps first, so its start can be shown.
    const all = scopedSpans.filter(isContentSpan);
    const inTurn = (sp: SpanListItem) =>
      prefetchTurn !== undefined && turnOfNode.get(sp.span_id) === prefetchTurn;
    const content = [...all.filter(inTurn), ...all.filter((sp) => !inTurn(sp))].slice(
      0,
      MAX_CONTENT_SPANS,
    );
    (async () => {
      if (cancelled) return;
      setConvo({ loaded: 0, total: content.length, done: content.length === 0 });
      let loaded = 0;
      for (const span of content) {
        let retries = 0;
        if (fetched.current.has(span.span_id)) {
          loaded += 1;
          continue;
        }
        for (;;) {
          if (cancelled) return;
          try {
            const detail = await getSpan(traceId, span.span_id);
            if (cancelled) return;
            fetched.current.add(span.span_id);
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
  }, [state, traceId, scopedSpans, view, prefetchTurn]);

  async function fetchDetail(id: string) {
    if (details.has(id)) return;
    try {
      const detail = await getSpan(traceId, id);
      setDetails((prev) => new Map(prev).set(id, detail));
    } catch {
      // Panel falls back to the light fields; reselecting retries.
    }
  }

  // Fetch full attributes/events lazily, when a span is first selected.
  function selectSpan(id: string) {
    setSelectedId(id);
    setShowRaw(false);
    void fetchDetail(id);
  }

  // The root's attributes say whether timestamps were synthesized (session
  // imports record no LLM response durations).
  const rootId = state.phase === "ready" ? state.roots[0]?.id : undefined;
  useEffect(() => {
    if (rootId) void fetchDetail(rootId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootId]);

  // Reveal a focused span once the tree exists (a focus requested while
  // spans load applies when they land).
  useEffect(() => {
    if (!focus || focus.seq === handledFocus.current || state.phase !== "ready") return;
    handledFocus.current = focus.seq;
    const span = state.spans.find((s) => s.source_span_id === focus.sourceSpanId);
    const path = span ? ancestorIds(state.roots, span.span_id) : null;
    if (!span || path === null) return;
    // A controlled host switches to Spans itself (with the same history step).
    if (controlledView === undefined) setOwnView("spans");
    setExpandedIds((prev) => [...new Set([...prev, ...path])]);
    void selectSpan(span.span_id);
    setScrollSeq((n) => n + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, state]);

  useEffect(() => {
    if (scrollSeq === 0) return;
    const frame = requestAnimationFrame(() => {
      treeRef.current
        ?.querySelector('li[aria-selected="true"] > div')
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [scrollSeq]);

  const nodeById = useMemo(
    () => (state.phase === "ready" ? flatten(state.roots) : new Map<string, TraceSpan>()),
    [state],
  );

  // A host panel shows the agent's last reply under the selection: fetch
  // that LLM span's detail with it.
  useEffect(() => {
    const node = selectedId && renderSpanPanel ? nodeById.get(selectedId) : undefined;
    const reply = node ? lastLlmDescendant(node) : undefined;
    if (reply) void fetchDetail(reply.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, nodeById]);

  const conversation = useMemo(
    () =>
      state.phase === "ready"
        ? // In scope the spawn call itself is the card above, not a step.
          buildConversation(
            scopeNodeId ? scopedSpans.filter((sp) => sp.span_id !== scopeNodeId) : scopedSpans,
            details,
          )
        : [],
    [state, scopedSpans, scopeNodeId, details],
  );

  // Scoped: the spawn span's detail (its brief) and the turn spans' asks.
  const scopeSpawn = agentScope ? agents?.find((a) => a.span_id === agentScope) : undefined;
  useEffect(() => {
    if (!scopeNodeId) return;
    // The card's final report: the subagent's last LLM reply.
    const scopeRootNode = state.phase === "ready" ? flatten(state.roots).get(scopeNodeId) : undefined;
    const reply = scopeRootNode ? lastLlmDescendant(scopeRootNode) : undefined;
    if (reply) void fetchDetail(reply.id);
    // The scoped tree opens one level deep: the subagent's own steps.
    setExpandedIds((prev) => (prev.includes(scopeNodeId) ? prev : [...prev, scopeNodeId]));
    void fetchDetail(scopeNodeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeNodeId]);
  // Escape leaves the subagent scope unless a popover or dialog has it.
  useEffect(() => {
    if (!agentScope || !onScope) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (document.querySelector('[data-slot="popover-content"], [role="dialog"]')) return;
      onScope(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [agentScope, onScope]);
  const conversationLength = conversation.length;
  // In scope the brief is in the card: drop the message repeating it.
  const scopeBrief = scopeNodeId ? spawnBriefOf(details.get(scopeNodeId)) : undefined;
  const shownConversation = scopeBrief
    ? conversation.filter((i) => !(i.kind === "message" && i.text.trim() === scopeBrief.trim()))
    : conversation;
  // An explicit turn selection (left pane, deep link): bring that turn into
  // view here — its start in the conversation, its span in the tree.
  const handledTurn = useRef(0);
  useEffect(() => {
    if (!turnFocus || turnFocus.seq === handledTurn.current || state.phase !== "ready") return;
    if (view === "conversation") {
      const anchor = document.getElementById(`conv-turn-${turnFocus.turn}`);
      if (!anchor) return; // not reconstructed yet: retried as items load
      handledTurn.current = turnFocus.seq;
      anchor.scrollIntoView({ block: "start", behavior: "smooth" });
    } else if (view === "spans") {
      handledTurn.current = turnFocus.seq;
      const id = turnNodes.get(turnFocus.turn);
      const path = id ? ancestorIds(state.roots, id) : null;
      if (!id || path === null) return;
      setExpandedIds((prev) => [...new Set([...prev, ...path])]);
      selectSpan(id);
      setScrollSeq((n) => n + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turnFocus, state, view, turnNodes, conversationLength]);

  const turnInfo = useMemo(() => {
    const map = new Map<number, TurnInfo>();
    if (state.phase !== "ready") return map;
    for (const sp of state.spans) {
      const m = /^turn (\d+)\b/i.exec(sp.name);
      if (!m || sp.kind !== "agent") continue;
      map.set(Number(m[1]) - 1, {
        ask: cleanSpanName(sp.name).replace(/^turn \d+:?\s*/i, ""),
        start: new Date(sp.started_at).getTime(),
        end: new Date(sp.ended_at).getTime(),
      });
    }
    return map;
  }, [state]);

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
    return (
      <div className="flex flex-col items-start gap-2 rounded-lg border bg-background p-4 text-sm">
        <p className="text-error-deep">Could not load the trace’s spans.</p>
        <Button size="sm" variant="outline" onClick={() => setReloadKey((k) => k + 1)}>
          Retry
        </Button>
      </div>
    );
  }

  const selectedNode = selectedId ? nodeById.get(selectedId) : undefined;
  const selectedDetail = selectedId ? details.get(selectedId) : undefined;
  const panelSpan =
    selectedNode && selectedDetail ? withDetail(selectedNode, selectedDetail) : selectedNode;

  const contentSpanCount = scopedSpans.filter(isContentSpan).length;
  const scopeRoot = scopeNodeId ? nodeById.get(scopeNodeId) : undefined;
  // In scope: only spawns nested under the scoped one.
  const scopedAgents = (agents ?? []).filter((a) => {
    if (!agentScope) return true;
    for (let p = a.parent_span_id; p; p = agents?.find((x) => x.span_id === p)?.parent_span_id ?? null) {
      if (p === agentScope) return true;
    }
    return false;
  });
  const scopeReplySpan = scopeRoot ? lastLlmDescendant(scopeRoot) : undefined;
  const scopeReplyItem = scopeReplySpan
    ? state.spans.find((sp) => sp.span_id === scopeReplySpan.id)
    : undefined;
  const scopeReport = !scopeRoot
    ? undefined
    : scopeReplyItem && details.has(scopeReplyItem.span_id)
      ? lastAssistantText(buildConversation([scopeReplyItem], details))
      : scopeReplyItem
        ? undefined
        : null;
  const synthesized =
    rootId !== undefined && details.get(rootId)?.attributes["converted.synthesized_root"] === true;
  const durationUnknown = (span: TraceSpan) => synthesized && span.type === "llm_call";

  const replySpan = selectedNode ? lastLlmDescendant(selectedNode) : undefined;
  const replyItem = replySpan ? state.spans.find((s) => s.span_id === replySpan.id) : undefined;
  const custom =
    selectedNode && renderSpanPanel
      ? renderSpanPanel({
          node: selectedNode,
          sourceSpanId: state.spans.find((sp) => sp.span_id === selectedNode.id)?.source_span_id ?? null,
          attributes: selectedDetail?.attributes ?? null,
          finalReply: !replyItem
            ? null
            : details.has(replyItem.span_id)
              ? lastAssistantText(buildConversation([replyItem], details))
              : undefined,
        })
      : null;

  return (
    <div className={cn("flex h-[calc(100vh-22rem)] min-h-96 flex-col gap-3", className)}>
      {scopeSpawn && onScope && (
        <ScopeHeader
          spawn={scopeSpawn}
          agents={agents ?? []}
          turnInfo={turnInfo}
          onScope={onScope}
          onTurn={onShowAgents}
          brief={scopeBrief}
          report={scopeReport}
          onShowSpan={onShowSpan}
        />
      )}
      <ViewToggle view={view} onChange={setView} agentCount={scopedAgents.length} />

      {view === "agents" && scopedAgents.length > 0 ? (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border bg-background p-3">
          <AgentsView
            agents={scopedAgents}
            turns={turnInfo}
            onOpen={(id) => onScope?.(id)}
            onShowSpan={onShowSpan}
            focus={agentFocus}
          />
        </div>
      ) : view === "agents" && agents === null ? (
        <p className="text-sm text-muted-foreground">Loading subagents…</p>
      ) : view === "conversation" || view === "agents" ? (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border bg-background p-4">
          {conversation.length > 0 && (
            <ConversationView
              items={shownConversation}
              turnOf={(id) => turnOfNode.get(id)}
              activeTurn={turnFocus?.turn}
            />
          )}
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
        <SpanPanels
          direction={split}
          tree={
            <div
              ref={treeRef}
              className="h-full overflow-y-auto rounded-lg border bg-background py-2"
            >
              <TreeView
                spans={
                  scopeRoot
                    ? [scopeRoot]
                    : rootTitle && state.roots.length === 1
                      ? [{ ...state.roots[0], title: rootTitle }]
                      : state.roots
                }
                selectedSpan={panelSpan}
                onSpanSelect={(span) => {
                  selectSpan(span.id);
                  // Selecting a turn span selects that turn on the left too.
                  if (turnNodes.get(turnOfNode.get(span.id) ?? -1) === span.id)
                    onTurnSelect?.(turnOfNode.get(span.id)!);
                }}
                expandedSpansIds={expandedIds}
                onExpandSpansIdsChange={setExpandedIds}
                spanCardViewOptions={{ expandButton: "inside", durationUnknown }}
              />
            </div>
          }
          detail={
            <div className="flex h-full flex-col overflow-hidden rounded-lg border bg-background">
              {custom && (
                <div className="flex shrink-0 justify-end border-b px-3 py-1.5">
                  <button
                    type="button"
                    onClick={() => setShowRaw((v) => !v)}
                    className="text-xs font-medium text-link hover:underline"
                  >
                    {showRaw ? "Show analysis" : "Show span data"}
                  </button>
                </div>
              )}
              {custom && !showRaw ? (
                <div className="min-h-0 flex-1 overflow-y-auto">{custom}</div>
              ) : panelSpan ? (
                <DetailsView
                  key={panelSpan.id}
                  data={panelSpan}
                  durationUnknown={durationUnknown(panelSpan)}
                  className="min-h-0 flex-1 border-0"
                />
              ) : (
                <p className="p-4 text-sm text-muted-foreground">
                  Select a span to inspect its attributes and events.
                </p>
              )}
            </div>
          }
        />
      )}
    </div>
  );
}

function spawnBriefOf(detail: SpanDetail | undefined): string | null | undefined {
  return detail ? spawnBrief(detail.attributes) : undefined;
}

/** The subagent scope: breadcrumb (Session › Turn N › parents › this), a way
 *  back, and the subagent's card (brief + final report). */
function ScopeHeader({
  spawn,
  agents,
  turnInfo,
  onScope,
  onTurn,
  brief,
  report,
  onShowSpan,
}: {
  spawn: AgentSpawn;
  agents: AgentSpawn[];
  turnInfo: Map<number, TurnInfo>;
  onScope: (spanId: string | null) => void;
  onTurn?: (turnIndex: number) => void;
  brief: string | null | undefined;
  report: string | null | undefined;
  onShowSpan?: (spanId: string) => void;
}) {
  const parents: AgentSpawn[] = [];
  for (let p = spawn.parent_span_id; p; ) {
    const parent = agents.find((a) => a.span_id === p);
    if (!parent) break;
    parents.unshift(parent);
    p = parent.parent_span_id;
  }
  const turnLabel = spawn.turn_index === null ? "no turn" : `Turn ${spawn.turn_index + 1}`;
  const crumb =
    "max-w-48 truncate rounded-sm hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none";
  return (
    <div className="flex shrink-0 flex-col gap-2">
      <nav className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground" aria-label="Subagent scope">
        <button type="button" className={crumb} onClick={() => onScope(null)}>
          Session
        </button>
        <span aria-hidden>›</span>
        {spawn.turn_index !== null && onTurn ? (
          // The turn's group in the Agents view.
          <button
            type="button"
            className={crumb}
            title={turnInfo.get(spawn.turn_index)?.ask}
            onClick={() => onTurn(spawn.turn_index!)}
          >
            {turnLabel}
          </button>
        ) : (
          <span>{turnLabel}</span>
        )}
        {parents.map((p) => (
          <span key={p.span_id} className="flex min-w-0 items-center gap-1.5">
            <span aria-hidden>›</span>
            <button type="button" className={crumb} onClick={() => onScope(p.span_id)}>
              {p.description ?? "Subagent"}
            </button>
          </span>
        ))}
        <span aria-hidden>›</span>
        <span className="min-w-0 truncate text-foreground">{spawn.description ?? "Subagent"}</span>
        <Button size="xs" variant="outline" className="ml-auto shrink-0" onClick={() => onScope(null)}>
          Back to session
        </Button>
      </nav>
      <div className="rounded-lg border bg-background px-3 py-2">
        <SubagentCard
          compact
          agent={spawn}
          turnLabel={turnLabel}
          parentLabel={parents.length ? (parents[parents.length - 1].description ?? "a subagent") : "the main agent"}
          brief={brief}
          report={report}
          onShowSpan={onShowSpan}
        />
      </div>
    </div>
  );
}
