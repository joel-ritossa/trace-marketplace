// Reconstructs a chat-style conversation from span content attributes.
//
// Mirrors the backend's extraction chains (app/analysis/content.py): OTel
// GenAI message lists first (`gen_ai.input/output.messages`), then Traceloop
// flattened prompts (`gen_ai.prompt.N.*`), then generic input/output values,
// then span events. Later LLM calls replay the whole history in their input
// messages, so messages are deduped structurally — each renders once, in
// chronological span order. Fail open: spans with nothing extractable are
// simply absent from the conversation.

import type { SpanDetail, SpanEvent, SpanListItem } from "@/lib/api/traces";

export type MessageRole = "user" | "assistant" | "system" | "other";

export type ConversationItem =
  | { kind: "message"; id: string; role: MessageRole; label: string; text: string }
  | { kind: "reasoning"; id: string; text: string }
  | {
      kind: "tool";
      id: string;
      name: string;
      input: string | null;
      output: string | null;
      error: boolean;
    };

const TOOL_INPUT_KEYS = ["gen_ai.tool.call.arguments", "traceloop.entity.input", "input.value"];
const TOOL_OUTPUT_KEYS = ["gen_ai.tool.call.result", "traceloop.entity.output", "output.value"];
const GENERIC_INPUT_KEYS = ["input.value", "traceloop.entity.input"];
const GENERIC_OUTPUT_KEYS = ["output.value", "traceloop.entity.output"];
const MAX_INDEXED_ATTRS = 64;

type Dict = Record<string, unknown>;

function isDict(value: unknown): value is Dict {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function firstString(attributes: Dict, keys: string[]): string | null {
  for (const key of keys) {
    const value = attributes[key];
    if (typeof value === "string" && value.length > 0) return value;
  }
  return null;
}

function compact(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

function parseMessages(value: unknown): Dict[] | null {
  let parsed = value;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return null;
    }
  }
  if (Array.isArray(parsed) && parsed.every(isDict)) return parsed;
  return null;
}

/** Traceloop legacy: gen_ai.prompt.0.role / gen_ai.prompt.0.content … */
function flattenedMessages(attributes: Dict, prefix: string): Dict[] | null {
  const messages: Dict[] = [];
  for (let i = 0; i < MAX_INDEXED_ATTRS; i += 1) {
    const content = attributes[`${prefix}.${i}.content`];
    if (typeof content !== "string" || content.length === 0) break;
    messages.push({ role: attributes[`${prefix}.${i}.role`] ?? "unknown", content });
  }
  return messages.length > 0 ? messages : null;
}

function eventMessages(events: SpanEvent[], eventNames: string[], attrKeys: string[]): Dict[] | null {
  for (const event of events) {
    if (!eventNames.includes(event.name)) continue;
    const text = firstString(event.attributes, attrKeys);
    if (text) return parseMessages(text) ?? [{ role: "unknown", content: text }];
  }
  return null;
}

function normalizeRole(role: unknown): { role: MessageRole; label: string } {
  const raw = typeof role === "string" && role.length > 0 ? role : "unknown";
  const lower = raw.toLowerCase();
  if (lower === "user" || lower === "human") return { role: "user", label: "User" };
  if (lower === "assistant" || lower === "ai" || lower === "model")
    return { role: "assistant", label: "Assistant" };
  if (lower === "system" || lower === "developer") return { role: "system", label: "System" };
  return { role: "other", label: raw };
}

function dictParts(message: Dict): unknown[] {
  const parts = message.parts;
  if (Array.isArray(parts)) return parts;
  return message.content !== undefined && message.content !== null ? [message.content] : [];
}

type Builder = {
  items: ConversationItem[];
  seenMessages: Set<string>;
  emittedCallIds: Set<string>;
  resultsById: Map<string, string>;
};

function nextId(builder: Builder): string {
  return `conv-${builder.items.length}`;
}

function emitMessage(builder: Builder, message: Dict): void {
  const key = JSON.stringify(message);
  if (builder.seenMessages.has(key)) return;
  builder.seenMessages.add(key);

  const { role, label } = normalizeRole(message.role);
  const texts: string[] = [];
  const tools: ConversationItem[] = [];

  for (const part of dictParts(message)) {
    if (typeof part === "string") {
      if (part.length > 0) texts.push(part);
      continue;
    }
    if (!isDict(part)) {
      texts.push(compact(part));
      continue;
    }
    if (part.type === "tool_call") {
      const callId = typeof part.id === "string" ? part.id : null;
      if (callId !== null && builder.emittedCallIds.has(callId)) continue;
      if (callId !== null) builder.emittedCallIds.add(callId);
      tools.push({
        kind: "tool",
        id: nextId(builder) + `-t${tools.length}`,
        name: typeof part.name === "string" && part.name ? part.name : "tool",
        input: part.arguments !== undefined && part.arguments !== null ? compact(part.arguments) : null,
        output: callId !== null ? (builder.resultsById.get(callId) ?? null) : null,
        error: false,
      });
      continue;
    }
    if (part.type === "tool_call_response") {
      const callId = typeof part.id === "string" ? part.id : null;
      // Already shown as the matching tool_call's result.
      if (callId !== null && builder.emittedCallIds.has(callId)) continue;
      const payload = part.response ?? part.result;
      tools.push({
        kind: "tool",
        id: nextId(builder) + `-t${tools.length}`,
        name: typeof part.name === "string" && part.name ? part.name : "tool result",
        input: null,
        output: payload !== undefined && payload !== null ? compact(payload) : null,
        error: false,
      });
      continue;
    }
    const content = part.content ?? part.text;
    if (content !== undefined && content !== null) texts.push(compact(content));
  }

  const text = texts.join("\n").trim();
  if (text) {
    // A bare tool-role message is a tool result, not a chat bubble.
    if (typeof message.role === "string" && message.role.toLowerCase() === "tool") {
      builder.items.push({
        kind: "tool",
        id: nextId(builder),
        name: "tool result",
        input: null,
        output: text,
        error: false,
      });
    } else {
      builder.items.push({ kind: "message", id: nextId(builder), role, label, text });
    }
  }
  for (const tool of tools) builder.items.push({ ...tool, id: nextId(builder) });
}

/** Model reasoning (Claude thinking blocks, Codex reasoning summaries) is
 *  preserved by the session importers as `gen_ai.reasoning` on the llm span;
 *  it renders collapsed ahead of the span's assistant output. */
function emitReasoning(builder: Builder, detail: SpanDetail): void {
  const reasoning = detail.attributes["gen_ai.reasoning"];
  if (typeof reasoning !== "string" || reasoning.length === 0) return;
  const key = `reasoning:${reasoning}`;
  if (builder.seenMessages.has(key)) return;
  builder.seenMessages.add(key);
  builder.items.push({ kind: "reasoning", id: nextId(builder), text: reasoning });
}

function inputMessages(detail: SpanDetail): Dict[] | null {
  return (
    parseMessages(detail.attributes["gen_ai.input.messages"]) ??
    flattenedMessages(detail.attributes, "gen_ai.prompt") ??
    eventMessages(detail.events, ["gen_ai.content.prompt"], ["gen_ai.prompt"])
  );
}

function outputMessages(detail: SpanDetail): Dict[] | null {
  return (
    parseMessages(detail.attributes["gen_ai.output.messages"]) ??
    flattenedMessages(detail.attributes, "gen_ai.completion") ??
    eventMessages(detail.events, ["gen_ai.content.completion", "gen_ai.choice"], ["gen_ai.completion"])
  );
}

/** Spans whose details the conversation view needs. */
export function isContentSpan(span: SpanListItem): boolean {
  return span.kind === "llm" || span.kind === "tool";
}

export function buildConversation(
  spans: SpanListItem[],
  details: Map<string, SpanDetail>,
): ConversationItem[] {
  const ordered = spans
    .filter(isContentSpan)
    .map((span) => ({ span, detail: details.get(span.span_id) }))
    .filter((entry): entry is { span: SpanListItem; detail: SpanDetail } => entry.detail !== undefined)
    .sort(
      (a, b) =>
        new Date(a.span.started_at).getTime() - new Date(b.span.started_at).getTime() ||
        a.span.span_id.localeCompare(b.span.span_id),
    );

  const builder: Builder = {
    items: [],
    seenMessages: new Set(),
    emittedCallIds: new Set(),
    resultsById: new Map(),
  };

  // Pass 1: tool results live in later spans' input messages, keyed by call
  // id — collect them first so each tool call renders with its result.
  for (const { span, detail } of ordered) {
    if (span.kind !== "llm") continue;
    for (const message of parseMessages(detail.attributes["gen_ai.input.messages"]) ?? []) {
      for (const part of dictParts(message)) {
        if (!isDict(part) || part.type !== "tool_call_response" || typeof part.id !== "string")
          continue;
        const payload = part.response ?? part.result;
        if (payload !== undefined && payload !== null && !builder.resultsById.has(part.id)) {
          builder.resultsById.set(part.id, compact(payload));
        }
      }
    }
  }

  for (const { span, detail } of ordered) {
    if (span.kind === "tool") {
      builder.items.push({
        kind: "tool",
        id: nextId(builder),
        name: span.tool_name ?? span.name,
        input: firstString(detail.attributes, TOOL_INPUT_KEYS),
        output: firstString(detail.attributes, TOOL_OUTPUT_KEYS),
        error: span.status === "error",
      });
      continue;
    }

    const inputs = inputMessages(detail);
    const outputs = outputMessages(detail);
    if (inputs !== null || outputs !== null) {
      for (const message of inputs ?? []) emitMessage(builder, message);
      emitReasoning(builder, detail);
      for (const message of outputs ?? []) emitMessage(builder, message);
      continue;
    }

    // Generic fallback: opaque input/output blobs, deduped as raw strings.
    const input = firstString(detail.attributes, GENERIC_INPUT_KEYS);
    if (input !== null && !builder.seenMessages.has(input)) {
      builder.seenMessages.add(input);
      builder.items.push({
        kind: "message",
        id: nextId(builder),
        role: "other",
        label: "Input",
        text: input,
      });
    }
    emitReasoning(builder, detail);
    const output = firstString(detail.attributes, GENERIC_OUTPUT_KEYS);
    if (output !== null && !builder.seenMessages.has(output)) {
      builder.seenMessages.add(output);
      builder.items.push({
        kind: "message",
        id: nextId(builder),
        role: "assistant",
        label: "Assistant",
        text: output,
      });
    }
  }

  return builder.items;
}
