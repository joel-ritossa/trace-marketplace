import { useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { ApiError } from "../lib/api";
import { buildConversation, isContentSpan } from "../lib/conversation";
import { getSpan, listAllSpans, type SpanDetail, type SpanListItem } from "../lib/traces";
import { ConversationView } from "./ConversationView";

// Desktop port of the web's TraceEvidence, conversation view only — raw span
// inspection stays on the web trace page (the host links there).

type LoadState =
  | { phase: "loading"; spansLoaded: number; spansTotal: number | null }
  | { phase: "error" }
  | { phase: "ready"; spans: SpanListItem[] };

// Conversation reconstruction needs full attributes, one request per
// llm/tool span — capped so a pathological trace can't issue thousands.
const MAX_CONTENT_SPANS = 200;

export function TraceEvidence({ traceId, webUrl }: { traceId: string; webUrl: string }) {
  const [state, setState] = useState<LoadState>({
    phase: "loading",
    spansLoaded: 0,
    spansTotal: null,
  });
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
        if (!cancelled) setState({ phase: "ready", spans });
      })
      .catch(() => {
        if (!cancelled) setState({ phase: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [traceId]);

  // Prefetch llm/tool span details one at a time (the per-user rate limit
  // makes parallel fetching counterproductive); 429s back off and retry,
  // other failures skip the span (fail open).
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

  const conversation = useMemo(
    () => (state.phase === "ready" ? buildConversation(state.spans, details) : []),
    [state, details],
  );

  if (state.phase === "loading") {
    return (
      <div className="evidence">
        <p className="hint">
          {state.spansTotal !== null && state.spansTotal > state.spansLoaded
            ? `Loading spans… ${state.spansLoaded.toLocaleString()} of ${state.spansTotal.toLocaleString()}`
            : "Loading spans…"}
        </p>
      </div>
    );
  }

  if (state.phase === "error") {
    return (
      <div className="evidence">
        <p className="error-text">Could not load the trace’s spans.</p>
      </div>
    );
  }

  const contentSpanCount = state.spans.filter(isContentSpan).length;

  return (
    <div className="evidence">
      {conversation.length > 0 && <ConversationView items={conversation} />}
      {!convo.done && (
        <p className="hint" style={{ marginTop: conversation.length > 0 ? 12 : 0 }}>
          Reconstructing conversation… {convo.loaded} of {convo.total}
        </p>
      )}
      {convo.done && conversation.length === 0 && (
        <div className="hint">
          <p>No conversation content could be extracted from this trace.</p>
          <button
            type="button"
            className="link-btn"
            onClick={() => void openUrl(`${webUrl}/traces/${traceId}`)}
          >
            Inspect the raw spans on the web trace page
          </button>
        </div>
      )}
      {convo.done && contentSpanCount > MAX_CONTENT_SPANS && (
        <p className="hint" style={{ marginTop: 12 }}>
          Showing the first {MAX_CONTENT_SPANS} steps — open the web trace page for the full trace.
        </p>
      )}
    </div>
  );
}
