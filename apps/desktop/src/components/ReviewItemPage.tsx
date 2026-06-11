import { useCallback, useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { ApiError } from "../lib/api";
import { formatDate } from "../lib/format";
import {
  getReviewItem,
  listReviewItems,
  resolveReviewItem,
  type Outcome,
  type ResolvedLabel,
  type ReviewItem,
} from "../lib/review";
import { FAILURE_MODES, humanize, OUTCOMES, TASK_CATEGORIES } from "../lib/taxonomy";
import { getTraceAnalysis, type TraceAnalysisSummary } from "../lib/traces";
import { TraceEvidence } from "./TraceEvidence";

// Desktop port of the web's review/resolve-view.tsx: same layout (evidence
// beside machine context + verdict form), same form semantics — nothing
// pre-selected, partial answers fine, failure_mode only with a failure
// verdict, indeterminate is an answer not a skip.

type LoadState =
  | { phase: "loading" }
  | { phase: "not-found" }
  | { phase: "error"; message: string }
  | { phase: "ready"; item: ReviewItem };

type JudgeReasoning =
  | { kind: "folded"; text: string }
  | { kind: "votes"; votes: { value: string; reasoning: string }[] };

/** The folded reasoning when the outcome had a consensus; otherwise the
 *  individual outcome votes' reasoning from the audit — a split vote is
 *  exactly when the reviewer most needs to see why. Same logic as the
 *  web's resolve-view.tsx. */
function judgeReasoning(analysis: TraceAnalysisSummary): JudgeReasoning | null {
  if (analysis.reasoning) return { kind: "folded", text: analysis.reasoning };
  const votes = analysis.audit.analyzers
    .flatMap((a) => a.votes ?? [])
    .filter((v) => v.call === "outcome" && typeof v.reasoning === "string" && v.reasoning !== "")
    .map((v) => ({ value: String(v.value), reasoning: String(v.reasoning) }));
  return votes.length > 0 ? { kind: "votes", votes } : null;
}

function ContextField({
  name,
  value,
  confidence,
}: {
  name: string;
  value: string | null;
  confidence: number | null;
}) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>
        {value !== null ? (
          <>
            {humanize(value)}
            {confidence !== null && <span className="confidence">{confidence.toFixed(2)}</span>}
          </>
        ) : (
          <span style={{ color: "var(--muted-foreground)" }}>—</span>
        )}
      </dd>
    </div>
  );
}

/** The machine's take, shown as context — never pre-selected (4_pages.md). */
function MachineContext({
  item,
  reasoning,
}: {
  item: ReviewItem;
  reasoning: JudgeReasoning | null;
}) {
  const v = item.context.verdict;
  return (
    <section className="card">
      <h2>{item.context.reasons.length > 0 ? "Why this is here" : "Machine verdict"}</h2>
      {item.context.reasons.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {item.context.reasons.map((reason) => (
            <li key={reason.code} style={{ fontSize: 13 }}>
              {reason.message}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">
          You asked to relabel this trace; the machine’s take is below for reference.
        </p>
      )}
      <dl className="verdict-grid" style={{ margin: 0 }}>
        <ContextField name="Outcome" value={v.outcome} confidence={v.outcome_confidence} />
        <ContextField
          name="Failure mode"
          value={v.failure_mode}
          confidence={v.failure_mode_confidence}
        />
        <ContextField
          name="Task category"
          value={v.task_category}
          confidence={v.task_category_confidence}
        />
      </dl>
      {reasoning && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <p className="hint" style={{ margin: 0 }}>
            {reasoning.kind === "folded" ? "Judge reasoning" : "Judge votes (no consensus)"}
          </p>
          {reasoning.kind === "folded" ? (
            <p style={{ margin: "4px 0 0", fontSize: 13 }}>{reasoning.text}</p>
          ) : (
            <ul style={{ margin: "4px 0 0", paddingLeft: 0, listStyle: "none" }}>
              {reasoning.votes.map((vote, i) => (
                <li key={i} style={{ fontSize: 13, marginTop: i > 0 ? 6 : 0 }}>
                  <span
                    style={{
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                      fontSize: 11,
                      color: "var(--muted-foreground)",
                    }}
                  >
                    {vote.value}
                  </span>{" "}
                  — {vote.reasoning}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function ResolvedLabels({ labels }: { labels: Record<string, ResolvedLabel> }) {
  return (
    <dl className="label-list">
      {Object.entries(labels).map(([field, label]) => (
        <div key={field} className="row spread">
          <dt>{humanize(field)}</dt>
          <dd>
            {humanize(label.value)}
            <span className="confidence">
              {label.confidence.toFixed(2)} · {label.provenance}
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ReviewItemPage({
  itemId,
  webUrl,
  onBack,
  onOpenItem,
  onResolved,
}: {
  itemId: string;
  webUrl: string;
  onBack: () => void;
  onOpenItem: (itemId: string) => void;
  onResolved: () => void;
}) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [nextId, setNextId] = useState<string | null>(null);
  const [reasoning, setReasoning] = useState<JudgeReasoning | null>(null);

  // The form mirrors the label model exactly; nothing pre-selected.
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [failureMode, setFailureMode] = useState<string | null>(null);
  const [taskCategory, setTaskCategory] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [resolvedLabels, setResolvedLabels] = useState<Record<string, ResolvedLabel> | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReviewItem(itemId)
      .then((item) => {
        if (!cancelled) setState({ phase: "ready", item });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) setState({ phase: "not-found" });
        else
          setState({
            phase: "error",
            message: err instanceof ApiError ? err.message : "Could not load the review item.",
          });
      });
    return () => {
      cancelled = true;
    };
  }, [itemId]);

  // The judge's reasoning lives on the analysis row, not the item's context
  // snapshot — fetched separately, failing open (the card just omits it).
  const traceId = state.phase === "ready" ? state.item.trace_id : null;
  useEffect(() => {
    if (traceId === null) return;
    let cancelled = false;
    getTraceAnalysis(traceId)
      .then((analysis) => {
        if (!cancelled) setReasoning(judgeReasoning(analysis));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [traceId]);

  // "Resolve & next" walks the queue, newest first — same as the web.
  const findNext = useCallback(() => {
    listReviewItems({ status: "open", limit: 2 })
      .then((res) => {
        const next = res.items.find((i) => i.review_item_id !== itemId);
        setNextId(next?.review_item_id ?? null);
      })
      .catch(() => setNextId(null));
  }, [itemId]);

  useEffect(findNext, [findNext]);

  const backLink = (
    <button type="button" className="link-btn back-link" onClick={onBack}>
      ← Review queue
    </button>
  );

  if (state.phase === "loading") {
    return (
      <div className="page wide">
        {backLink}
        <p className="hint">Loading review item…</p>
      </div>
    );
  }
  if (state.phase === "not-found") {
    return (
      <div className="page wide">
        {backLink}
        <div>
          <p style={{ fontWeight: 500 }}>Review item not found</p>
          <p className="hint" style={{ marginTop: 4 }}>
            It may belong to a trace that was deleted, or the link is wrong.
          </p>
        </div>
      </div>
    );
  }
  if (state.phase === "error") {
    return (
      <div className="page wide">
        {backLink}
        <p className="error-text">{state.message}</p>
      </div>
    );
  }

  const { item } = state;
  const answered = outcome !== null || failureMode !== null || taskCategory !== null;
  const justResolved = resolvedLabels !== null;

  async function onResolve(): Promise<boolean> {
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await resolveReviewItem(item.review_item_id, {
        ...(outcome !== null && { outcome }),
        ...(failureMode !== null && { failure_mode: failureMode }),
        ...(taskCategory !== null && { task_category: taskCategory }),
      });
      setResolvedLabels(res.labels);
      setState({ phase: "ready", item: res.item });
      onResolved();
      findNext();
      return true;
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Could not resolve the item — try again.",
      );
      return false;
    } finally {
      setSubmitting(false);
    }
  }

  function pickOutcome(value: Outcome) {
    const next = outcome === value ? null : value;
    setOutcome(next);
    // failure_mode only accompanies a failure verdict (4_pages.md).
    if (next !== "failure") setFailureMode(null);
  }

  return (
    <div className="page wide">
      <div>
        {backLink}
        <div className="row spread" style={{ marginTop: 8, alignItems: "baseline" }}>
          <h1 style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
            {item.trace.name}
          </h1>
          <button
            type="button"
            className="link-btn"
            style={{ flexShrink: 0 }}
            onClick={() => void openUrl(`${webUrl}/traces/${item.trace_id}`)}
          >
            open trace page
          </button>
        </div>
        <p className="hint" style={{ marginTop: 2 }}>
          From upload {item.upload_filename} · {formatDate(item.created_at)}
        </p>
      </div>

      <div className="resolve-grid">
        <TraceEvidence traceId={item.trace_id} webUrl={webUrl} />

        <div className="resolve-side">
          <MachineContext item={item} reasoning={reasoning} />

          {item.status !== "open" && !justResolved ? (
            <section className="card">
              <h2>{item.status === "resolved" ? "Resolved" : "Superseded"}</h2>
              {item.status === "resolved" ? (
                <>
                  <p className="hint">
                    Resolved by you{item.resolved_at ? ` on ${formatDate(item.resolved_at)}` : ""}.
                    Answered fields carry human provenance and confidence 1.00.
                  </p>
                  {item.answer && (
                    <dl className="label-list">
                      {(["outcome", "failure_mode", "task_category"] as const).map(
                        (field) =>
                          item.answer?.[field] && (
                            <div key={field} className="row spread">
                              <dt>{humanize(field)}</dt>
                              <dd>{humanize(item.answer[field]!)}</dd>
                            </div>
                          ),
                      )}
                    </dl>
                  )}
                </>
              ) : (
                <p className="hint">
                  A newer analysis run superseded this item. If it routed again, the fresh item is
                  in the queue.
                </p>
              )}
            </section>
          ) : justResolved ? (
            <section className="card">
              <h2 style={{ color: "var(--status-ok)" }}>Resolved</h2>
              <ResolvedLabels labels={resolvedLabels} />
              <div className="row">
                {nextId !== null && (
                  <button className="btn" onClick={() => onOpenItem(nextId)}>
                    Next item →
                  </button>
                )}
                <button
                  className={nextId !== null ? "btn outline" : "btn"}
                  onClick={onBack}
                >
                  Back to queue
                </button>
              </div>
            </section>
          ) : (
            <section className="card">
              <h2>Your verdict</h2>
              <p className="hint">
                Answer any of the fields — partial resolutions are fine. Indeterminate is a valid
                answer, not a skip.
              </p>

              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="field">
                  <label>Outcome</label>
                  <div className="choices">
                    {OUTCOMES.map(({ value, description }) => (
                      <button
                        key={value}
                        type="button"
                        className="choice"
                        title={description}
                        data-selected={outcome === value}
                        onClick={() => pickOutcome(value)}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </div>

                {outcome === "failure" && (
                  <div className="field">
                    <label>Failure mode</label>
                    <select
                      className="input"
                      value={failureMode ?? ""}
                      onChange={(e) =>
                        setFailureMode(e.target.value === "" ? null : e.target.value)
                      }
                    >
                      <option value="">Leave unanswered</option>
                      {FAILURE_MODES.map(({ value, description }) => (
                        <option key={value} value={value}>
                          {humanize(value)} — {description}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="field">
                  <label>Task category</label>
                  <select
                    className="input"
                    value={taskCategory ?? ""}
                    onChange={(e) =>
                      setTaskCategory(e.target.value === "" ? null : e.target.value)
                    }
                  >
                    <option value="">Leave unanswered</option>
                    {TASK_CATEGORIES.map((value) => (
                      <option key={value} value={value}>
                        {humanize(value)}
                      </option>
                    ))}
                  </select>
                </div>

                {formError && <p className="error-text">{formError}</p>}

                <div className="row">
                  {nextId !== null && (
                    <button
                      className="btn"
                      disabled={!answered || submitting}
                      onClick={async () => {
                        if (await onResolve()) onOpenItem(nextId);
                      }}
                    >
                      Resolve &amp; next →
                    </button>
                  )}
                  <button
                    className={nextId !== null ? "btn outline" : "btn"}
                    disabled={!answered || submitting}
                    onClick={() => void onResolve()}
                  >
                    {submitting ? "Resolving…" : "Resolve"}
                  </button>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
