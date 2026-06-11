// Converts API span rows into AgentPrism TraceSpan trees.

import type {
  TraceSpan,
  TraceSpanAttribute,
  TraceSpanCategory,
  TraceSpanStatus,
} from "@evilmartians/agent-prism-types";
import type { SpanDetail, SpanKind, SpanListItem, SpanStatus } from "@/lib/api/traces";

const KIND_TO_CATEGORY: Record<SpanKind, TraceSpanCategory> = {
  llm: "llm_call",
  agent: "agent_invocation",
  tool: "tool_execution",
  chain: "chain_operation",
  retriever: "retrieval",
  embedding: "embedding",
  other: "span",
};

const STATUS_TO_PRISM: Record<SpanStatus, TraceSpanStatus> = {
  ok: "success",
  error: "error",
  unset: "pending",
};

function toTraceSpan(span: SpanListItem): TraceSpan {
  return {
    id: span.span_id,
    title: span.name,
    startTime: new Date(span.started_at),
    endTime: new Date(span.ended_at),
    duration: span.duration_ms,
    type: KIND_TO_CATEGORY[span.kind],
    raw: "",
    status: STATUS_TO_PRISM[span.status],
    tokensCount: span.total_tokens ?? undefined,
    children: [],
  };
}

/** Builds the tree from source parent ids, defensively against corrupt
 *  input: orphans (parent id missing from the trace) and parent-id cycles
 *  render at root level rather than disappearing; duplicate source span ids
 *  each keep their own node. */
export function buildSpanTree(spans: SpanListItem[]): TraceSpan[] {
  const entries = spans.map((span) => ({ span, node: toTraceSpan(span) }));
  // First occurrence wins as the parent-lookup target for a duplicated id.
  const bySourceId = new Map<string, TraceSpan>();
  for (const { span, node } of entries) {
    if (!bySourceId.has(span.source_span_id)) bySourceId.set(span.source_span_id, node);
  }

  const parentOf = new Map<TraceSpan, TraceSpan>();
  const createsCycle = (parent: TraceSpan, child: TraceSpan): boolean => {
    for (let node: TraceSpan | undefined = parent; node; node = parentOf.get(node)) {
      if (node === child) return true;
    }
    return false;
  };

  const roots: TraceSpan[] = [];
  for (const { span, node } of entries) {
    const parent = span.source_parent_span_id
      ? bySourceId.get(span.source_parent_span_id)
      : undefined;
    if (parent && parent !== node && !createsCycle(parent, node)) {
      parent.children!.push(node);
      parentOf.set(node, parent);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

/** Breadth-first default expansion, capped so huge traces don't render tens
 *  of thousands of cards at once (AgentPrism has no virtualization). */
export function defaultExpandedIds(roots: TraceSpan[], cap = 300): string[] {
  const expanded: string[] = [];
  let visible = roots.length;
  const queue = [...roots];
  while (queue.length > 0 && visible < cap) {
    const node = queue.shift()!;
    const children = node.children ?? [];
    if (children.length === 0) continue;
    expanded.push(node.id);
    visible += children.length;
    queue.push(...children);
  }
  return expanded;
}

function toAttributeValue(value: unknown): TraceSpanAttribute["value"] {
  if (typeof value === "boolean") return { boolValue: value };
  if (typeof value === "number") return { intValue: String(value) };
  if (typeof value === "string") return { stringValue: value };
  return { stringValue: JSON.stringify(value) };
}

function findString(attributes: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = attributes[key];
    if (typeof value === "string" && value.length > 0) return value;
  }
  return undefined;
}

// Mirrors the backend's extraction chains (app/analysis/content.py): OTel
// GenAI conventions first, then OpenInference/Traceloop fallbacks. Tool
// spans carry their I/O in the tool-call attributes, not message lists.
const TOOL_INPUT_KEYS = ["gen_ai.tool.call.arguments", "traceloop.entity.input", "input.value"];
const TOOL_OUTPUT_KEYS = ["gen_ai.tool.call.result", "traceloop.entity.output", "output.value"];
const INPUT_KEYS = ["gen_ai.input.messages", "input.value", "traceloop.entity.input"];
const OUTPUT_KEYS = ["gen_ai.output.messages", "output.value", "traceloop.entity.output"];

/** Merges a fetched span detail into its tree node for the detail panel:
 *  full attributes, raw JSON, and In/Out content where the span carries it. */
export function withDetail(node: TraceSpan, detail: SpanDetail): TraceSpan {
  const tool = node.type === "tool_execution";
  return {
    ...node,
    raw: JSON.stringify({ attributes: detail.attributes, events: detail.events }, null, 2),
    attributes: Object.entries(detail.attributes).map(([key, value]) => ({
      key,
      value: toAttributeValue(value),
    })),
    input: findString(detail.attributes, tool ? TOOL_INPUT_KEYS : INPUT_KEYS),
    output: findString(detail.attributes, tool ? TOOL_OUTPUT_KEYS : OUTPUT_KEYS),
  };
}
