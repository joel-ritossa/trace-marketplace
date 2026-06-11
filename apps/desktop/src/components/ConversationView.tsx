import { useState } from "react";
import type { ConversationItem } from "../lib/conversation";

// Plain-CSS port of the web's components/traces/conversation-view.tsx —
// same clamp/expand, tool cards, and collapsed system prompts.

const CLAMP_CHARS = 1500;

function ClampedText({ text, mono = false }: { text: string; mono?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const clipped = !expanded && text.length > CLAMP_CHARS;
  return (
    <div>
      <div className={mono ? "convo-text mono" : "convo-text"}>
        {clipped ? `${text.slice(0, CLAMP_CHARS)}…` : text}
      </div>
      {text.length > CLAMP_CHARS && (
        <button type="button" className="link-btn" onClick={() => setExpanded((v) => !v)}>
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
    <div className="convo-tool" data-error={item.error}>
      <button type="button" className="convo-tool-head" onClick={() => setOpen((v) => !v)}>
        <span className="convo-chevron">{open ? "▾" : "▸"}</span>
        <span className="convo-tool-name mono">{item.name}</span>
        {item.error && <span className="convo-tool-error">error</span>}
        {!open && preview && <span className="convo-tool-preview mono">{preview}</span>}
      </button>
      {open && (
        <div className="convo-tool-body">
          {item.input !== null && (
            <div>
              <p className="convo-section-label">Input</p>
              <ClampedText text={item.input} mono />
            </div>
          )}
          {item.output !== null && (
            <div>
              <p className="convo-section-label">Result</p>
              <ClampedText text={item.output} mono />
            </div>
          )}
          {item.input === null && item.output === null && (
            <p className="hint">No recorded input or result.</p>
          )}
        </div>
      )}
    </div>
  );
}

function SystemCard({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="convo-system">
      <button type="button" className="convo-tool-head" onClick={() => setOpen((v) => !v)}>
        <span className="convo-chevron">{open ? "▾" : "▸"}</span>
        <span className="convo-section-label" style={{ marginBottom: 0 }}>
          System prompt
        </span>
        {!open && (
          <span className="convo-tool-preview">{text.replace(/\s+/g, " ").slice(0, 100)}</span>
        )}
      </button>
      {open && (
        <div className="convo-tool-body" style={{ color: "var(--muted-foreground)" }}>
          <ClampedText text={text} />
        </div>
      )}
    </div>
  );
}

/** Chronological chat rendering of a reconstructed conversation. */
export function ConversationView({ items }: { items: ConversationItem[] }) {
  return (
    <div className="convo">
      {items.map((item) => {
        if (item.kind === "tool") return <ToolCard key={item.id} item={item} />;
        if (item.role === "system") return <SystemCard key={item.id} text={item.text} />;
        const user = item.role === "user";
        return (
          <div key={item.id} className="convo-message" data-user={user}>
            <p className="convo-role">{item.label}</p>
            <div className="convo-bubble">
              <ClampedText text={item.text} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
