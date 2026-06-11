"use client";

import { useState } from "react";
import { Brain, ChevronDown, ChevronRight, Wrench } from "lucide-react";

import type { ConversationItem } from "@/components/traces/conversation";
import { cn } from "@/lib/utils";

const CLAMP_CHARS = 1500;

function ClampedText({ text, mono = false }: { text: string; mono?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const clipped = !expanded && text.length > CLAMP_CHARS;
  return (
    <div>
      <div
        className={cn(
          "whitespace-pre-wrap break-words",
          mono ? "font-mono text-xs" : "text-sm leading-relaxed",
        )}
      >
        {clipped ? `${text.slice(0, CLAMP_CHARS)}…` : text}
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

function ToolCard({ item }: { item: Extract<ConversationItem, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const preview = (item.input ?? item.output ?? "").replace(/\s+/g, " ").slice(0, 80);
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
            {preview}
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
              <ClampedText text={item.text} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
