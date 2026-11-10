"use client";

import { useState, type ReactNode } from "react";
import { Brain, ChevronDown, ChevronRight, Wrench } from "lucide-react";

import type { ConversationItem } from "@/components/traces/conversation";
import { cleanMessage } from "@/components/traces/names";
import { cn } from "@/lib/utils";

const CLAMP_CHARS = 1500;

// No markdown renderer in the dependencies: the cheap, safe subset —
// **bold**, `code` and "#" headings — as React elements; the rest stays text.
const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

function inline(line: string, key: string): ReactNode[] {
  return line.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={`${key}-${i}`} className="font-semibold">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return (
        <code key={`${key}-${i}`} className="rounded-sm bg-secondary px-1 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    return part;
  });
}

const TABLE_SEP = /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const cells = (line: string) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

/** A simple pipe table: header row, separator, body rows. Null when the
 *  block doesn't parse (it then renders as text). */
function PipeTable({ lines, id }: { lines: string[]; id: string }) {
  const [header, , ...rows] = lines.map(cells);
  return (
    <span className="my-1 block overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr className="border-b">
            {header.map((c, i) => (
              <th key={i} className="px-2 py-1 text-left font-medium whitespace-nowrap">
                {inline(c, `${id}-h${i}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b last:border-b-0">
              {header.map((_, i) => (
                <td key={i} className="px-2 py-1 align-top">
                  {inline(row[i] ?? "", `${id}-${r}-${i}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </span>
  );
}

function LightMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith("|") && TABLE_SEP.test(lines[i + 1] ?? "") && cells(line).length > 1) {
      let end = i + 2;
      while (end < lines.length && lines[end].trim().startsWith("|")) end++;
      out.push(<PipeTable key={i} id={String(i)} lines={lines.slice(i, end)} />);
      i = end - 1;
      continue;
    }
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    out.push(
      <span key={i} className={cn(heading && "font-semibold")}>
        {i > 0 && !lines[i - 1].trim().startsWith("|") && "\n"}
        {inline(heading ? heading[1] : line, String(i))}
      </span>,
    );
  }
  return out;
}

function ClampedText({ text, mono = false }: { text: string; mono?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const clipped = !expanded && text.length > CLAMP_CHARS;
  const shown = clipped ? `${text.slice(0, CLAMP_CHARS)}…` : text;
  return (
    <div>
      <div
        className={cn(
          "whitespace-pre-wrap break-words",
          mono ? "font-mono text-xs" : "text-sm leading-relaxed",
        )}
      >
        {mono ? shown : <LightMarkdown text={shown} />}
      </div>
      {text.length > CLAMP_CHARS && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-xs font-medium text-link hover:underline"
        >
          {expanded ? "Show less" : `Show all (${text.length.toLocaleString()} chars)`}
        </button>
      )}
    </div>
  );
}

// Tool-call argument keys that say what a call did, in preference order.
const PREVIEW_KEYS = ["command", "file_path", "path", "pattern", "query", "url", "description", "prompt"];

/** "Bash · `git status`" instead of raw JSON: the telling argument, else the
 *  compacted input. */
function toolPreview(input: string | null, output: string | null): string {
  try {
    const args = JSON.parse(input ?? "");
    for (const key of PREVIEW_KEYS) {
      if (typeof args?.[key] === "string" && args[key]) return args[key];
    }
  } catch {
    // Not JSON: fall through to the raw text.
  }
  return input ?? output ?? "";
}

function ToolCard({ item }: { item: Extract<ConversationItem, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const preview = toolPreview(item.input, item.output).replace(/\s+/g, " ").slice(0, 120);
  return (
    <div
      className={cn(
        "w-full rounded-md border",
        item.error ? "border-error bg-error-soft/30" : "bg-muted/40",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <Wrench className="size-3 shrink-0 text-span-tool" />
        <span className="shrink-0 font-mono text-xs font-medium">{item.name}</span>
        {item.error && (
          <span className="shrink-0 text-xs font-medium text-error-deep">error</span>
        )}
        {!open && preview && (
          <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">
            · {preview}
          </span>
        )}
      </button>
      {open && (
        <div className="flex flex-col gap-2 border-t px-2.5 py-2">
          {item.input !== null && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Input
              </p>
              <ClampedText text={item.input} mono />
            </div>
          )}
          {item.output !== null && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Result
              </p>
              <ClampedText text={item.output} mono />
            </div>
          )}
          {item.input === null && item.output === null && (
            <p className="text-xs text-muted-foreground">No recorded input or result.</p>
          )}
        </div>
      )}
    </div>
  );
}

function ReasoningCard({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="w-full rounded-md border border-dashed">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs text-muted-foreground"
      >
        {open ? <ChevronDown className="size-3 shrink-0" /> : <ChevronRight className="size-3 shrink-0" />}
        <Brain className="size-3 shrink-0" />
        <span className="shrink-0 font-medium uppercase tracking-wide">Reasoning</span>
        {!open && (
          <span className="min-w-0 truncate">{text.replace(/\s+/g, " ").slice(0, 100)}</span>
        )}
      </button>
      {open && (
        <div className="border-t px-2.5 py-2 text-muted-foreground">
          <ClampedText text={text} />
        </div>
      )}
    </div>
  );
}

function SystemCard({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border border-dashed">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs text-muted-foreground"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        <span className="font-medium uppercase tracking-wide">System prompt</span>
        {!open && (
          <span className="min-w-0 truncate">{text.replace(/\s+/g, " ").slice(0, 100)}</span>
        )}
      </button>
      {open && (
        <div className="border-t px-2.5 py-2 text-muted-foreground">
          <ClampedText text={text} />
        </div>
      )}
    </div>
  );
}

// Client wrappers around pasted text; they fold into a toggle.
const PASTED = /<(pasted[\w-]*)\b[^>]*>([\s\S]*?)<\/\1>/g;

function PastedBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="my-1 rounded-md border border-dashed">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-2.5 py-1 text-left text-xs text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        Pasted content · {text.length.toLocaleString()} chars
      </button>
      {open && (
        <div className="border-t px-2.5 py-2">
          <ClampedText text={text} mono />
        </div>
      )}
    </div>
  );
}

/** A message's text with pasted blocks folded and runs of blank lines
 *  collapsed (they rendered as large gaps). */
function MessageText({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(PASTED)) {
    const before = cleanMessage(text.slice(last, match.index));
    if (before) parts.push(<ClampedText key={last} text={before} />);
    parts.push(<PastedBlock key={`p${match.index}`} text={match[2].trim()} />);
    last = match.index + match[0].length;
  }
  const rest = cleanMessage(text.slice(last));
  if (rest) parts.push(<ClampedText key={last} text={rest} />);
  return <>{parts}</>;
}

/** Chronological chat rendering of a reconstructed conversation. */
export function ConversationView({ items }: { items: ConversationItem[] }) {
  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => {
        if (item.kind === "tool") return <ToolCard key={item.id} item={item} />;
        if (item.kind === "reasoning") return <ReasoningCard key={item.id} text={item.text} />;
        if (item.role === "system") return <SystemCard key={item.id} text={item.text} />;
        const user = item.role === "user";
        return (
          <div
            key={item.id}
            className={cn("flex max-w-[92%] flex-col", user ? "self-end items-end" : "self-start")}
          >
            <p className="mb-1 px-0.5 text-xs font-medium text-muted-foreground">{item.label}</p>
            <div
              className={cn(
                "rounded-lg px-3 py-2",
                user ? "bg-accent border" : "border bg-background",
              )}
            >
              <MessageText text={item.text} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
