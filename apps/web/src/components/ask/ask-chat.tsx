"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import ReactMarkdown from "react-markdown";
import { ArrowUp, FileText, Loader2, Search, Sparkles, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AskAgentUIMessage } from "@/lib/agent/ask-agent";

const STARTERS = [
  "How does an upload become a searchable trace?",
  "How does the outcome judge decide pass/fail?",
  "What stops gitignored or private data from leaking into listings?",
  "How is the marketplace access model enforced?",
];

function ToolChip({ part }: { part: AskAgentUIMessage["parts"][number] }) {
  if (part.type !== "tool-search" && part.type !== "tool-read_file") return null;
  const running = part.state === "input-streaming" || part.state === "input-available";
  const input = (part.input ?? {}) as Record<string, unknown>;
  const files = Array.isArray(input.files)
    ? (input.files as { path?: string }[]).map((f) => f.path ?? "…")
    : [];
  const label =
    part.type === "tool-search"
      ? `Searched ${String(input.pattern ?? "…")}`
      : `Read ${files.join(", ") || "…"}`;
  const Icon = part.type === "tool-search" ? Search : FileText;
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-md border bg-canvas-soft px-2 py-1 font-mono text-xs text-muted-foreground">
      {running ? (
        <Loader2 className="size-3 shrink-0 animate-spin" />
      ) : (
        <Icon className="size-3 shrink-0" />
      )}
      <span className="truncate">{label}</span>
    </span>
  );
}

/** Markdown styled with design tokens (no typography plugin in this app). */
function Answer({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed [&_h1]:text-base [&_h1]:font-semibold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-medium [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_a]:text-primary [&_a]:underline-offset-2 hover:[&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground">
      <ReactMarkdown
        components={{
          code({ className, children, ...props }) {
            const block = className?.includes("language-");
            return block ? (
              <code className={cn("font-mono text-xs", className)} {...props}>
                {children}
              </code>
            ) : (
              <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs" {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return (
              <pre className="overflow-x-auto rounded-md border bg-canvas-soft p-3">{children}</pre>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

function Message({ message }: { message: AskAgentUIMessage }) {
  if (message.role === "user") {
    const text = message.parts
      .map((part) => (part.type === "text" ? part.text : ""))
      .join("");
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-secondary px-3.5 py-2.5 text-sm whitespace-pre-wrap">
          {text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {message.parts.map((part, i) => {
        if (part.type === "text") return <Answer key={i} text={part.text} />;
        if (part.type === "tool-search" || part.type === "tool-read_file") {
          return (
            <div key={i} className="flex">
              <ToolChip part={part} />
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

export function AskChat() {
  const { messages, sendMessage, status, stop, error } = useChat<AskAgentUIMessage>({
    transport: new DefaultChatTransport({ api: "/api/ask" }),
  });
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    sendMessage({ text: trimmed });
    setInput("");
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto pb-6">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <div className="flex flex-col items-center gap-2">
              <Sparkles className="size-6 text-muted-foreground" strokeWidth={1.5} />
              <h1 className="text-lg font-semibold tracking-tight">Ask the codebase</h1>
              <p className="max-w-md text-sm text-muted-foreground">
                A read-only agent with search and file access over this repository&apos;s tracked
                files — ask how anything in the product actually works.
              </p>
            </div>
            <div className="flex max-w-lg flex-wrap justify-center gap-2">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => submit(q)}
                  className="rounded-md border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <Message key={message.id} message={message} />
        ))}

        {status === "submitted" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Thinking…
          </div>
        )}
        {error && (
          <p className="text-sm text-destructive">
            Something went wrong — check that OPENAI_API_KEY is configured, then retry.
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
        className="sticky bottom-0 flex items-end gap-2 border-t bg-canvas-soft pt-4 pb-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(input);
            }
          }}
          rows={2}
          placeholder="Ask how something works…"
          className="min-h-9 w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        />
        {busy ? (
          <Button type="button" size="icon" variant="outline" onClick={() => stop()} title="Stop">
            <Square className="size-3.5" />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!input.trim()} title="Send">
            <ArrowUp className="size-4" />
          </Button>
        )}
      </form>
    </div>
  );
}
