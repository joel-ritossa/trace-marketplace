"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CircleHelp, Play, UserCheck } from "lucide-react";
import {
  LabelChip,
  LabelChips,
  OutcomeBadge,
  SKIP_REASON_COPY,
} from "@/components/traces/badges";
import { BusyLabel } from "@/components/traces/bulk-bar";
import { RelabelTurn } from "@/components/traces/relabel-turn";
import { Button } from "@/components/ui/button";
import { errorText } from "@/lib/api/client";
import {
  analyzeTrace,
  type AnalysisSignals,
  type TraceAnalysis,
  type TraceDetail,
  type TurnAnalysis,
} from "@/lib/api/traces";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const SIGNAL_LABELS: [keyof AnalysisSignals, string][] = [
  ["has_retry_loop", "Retry loop"],
  ["loop_kind", "Loop kind"],
  ["recovered_from_error", "Recovered from error"],
  ["truncation_suspected", "Truncation suspected"],
  ["llm_call_count", "LLM calls"],
  ["tool_call_count", "Tool calls"],
];

function formatSignal(value: boolean | number | string | null): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** The trace-detail Analysis section (9_session-analysis.md): the session
 *  verdict card over one row per judged turn. Labels link to their evidence
 *  spans (`onShowSpan`, by source span id); owners relabel per turn. Always
 *  renders, with honest states — never a lie. */
export function AnalysisSection({
  trace,
  onChange,
  onShowSpan,
  focusTurn,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
  onShowSpan: (sourceSpanId: string) => void;
  focusTurn?: number;
}) {
  const { analysis } = trace;
  const onAnalysisChange = (next: TraceAnalysis) => onChange({ ...trace, analysis: next });

  // Review links land on one turn: bring its row into view once it exists.
  const focusPresent = analysis.turns.some((t) => t.turn_index === focusTurn);
  useEffect(() => {
    if (focusPresent) {
      document.getElementById(`turn-${focusTurn}`)?.scrollIntoView({ block: "center" });
    }
  }, [focusPresent, focusTurn]);

  return (
    <section className="flex flex-col gap-4 rounded-lg border bg-background px-4 py-3">
      <SessionCard trace={trace} />
      {analysis.turns.length > 0 && (
        <div>
          <h3 className="text-xs text-muted-foreground">Turns</h3>
          <ol className="mt-1 max-h-[32rem] divide-y overflow-y-auto">
            {analysis.turns.map((turn) => (
              <TurnRow
                key={turn.turn_index}
                traceId={trace.trace_id}
                turn={turn}
                isOwner={trace.is_owner}
                focused={turn.turn_index === focusTurn}
                onShowSpan={onShowSpan}
                onAnalysisChange={onAnalysisChange}
              />
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function SessionCard({ trace }: { trace: TraceDetail }) {
  const { session, turns, failed_reason } = trace.analysis;
  const judged = turns.filter((t) => t.outcome !== null).length;
  const uncertain = turns.filter((t) => t.uncertain !== null).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          Analysis
          {session.outcome && <OutcomeBadge outcome={session.outcome} />}
        </h2>
        {trace.is_owner && <AnalyzeNow trace={trace} />}
      </div>

      {failed_reason !== null && (
        <div>
          <p className="text-sm font-medium text-error-deep">The last analysis run failed</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{failed_reason}</p>
        </div>
      )}

      {session.status === "pending" && (
        <p className="text-sm text-muted-foreground">
          No turns judged yet. Each turn is judged once the next one starts; the last turn and the
          session verdict wait until the session has gone idle.
        </p>
      )}
      {session.status === "in_progress" && (
        <p className="text-sm text-muted-foreground">
          {judged} of {plural(session.turn_count, "turn")} judged — the session verdict is written
          once the session goes idle.
        </p>
      )}
      {session.status === "skipped" && session.skip_reason && (
        <p className="text-sm text-muted-foreground">
          {SKIP_REASON_COPY[session.skip_reason]}
          {session.skip_reason === "owner_opt_out" && trace.is_owner && (
            <>
              {" — "}
              <Link href="/settings" className="underline hover:text-foreground">
                change in settings
              </Link>
            </>
          )}
          . Deterministic signals are still computed.
        </p>
      )}
      {trace.is_owner && trace.analysis.open_review_item_id !== null && uncertain > 0 && (
        <p className="flex items-center gap-1.5 text-sm text-warning-deep">
          <CircleHelp className="size-3.5 shrink-0" />
          The judge was uncertain about {plural(uncertain, "turn")} — relabeling them improves this
          trace’s labels.
        </p>
      )}

      {session.goal && (
        <div>
          <h3 className="text-xs text-muted-foreground">Goal</h3>
          <p className="mt-0.5 text-sm">{session.goal}</p>
        </div>
      )}
      {session.summary && (
        <div>
          <h3 className="text-xs text-muted-foreground">What happened</h3>
          <p className="mt-0.5 text-sm">{session.summary}</p>
        </div>
      )}
      <LabelChips taskCategories={session.task_categories} failureModes={session.failure_modes} />

      {session.signals && (
        <div>
          <h3 className="text-xs text-muted-foreground">Signals</h3>
          <dl className="mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
            {SIGNAL_LABELS.map(([key, label]) => (
              <div key={key} className="flex items-baseline justify-between gap-2 sm:block">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="font-mono text-xs">{formatSignal(session.signals![key])}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {session.analyzed_at && (
        <p className="text-xs text-muted-foreground">
          Session verdict written {formatDate(session.analyzed_at)}
        </p>
      )}
    </div>
  );
}

/** Owner: finalize now (POST /analyze, 202). Shown while there is something
 *  to finalize or the last run failed; stays busy until the realtime refetch
 *  shows a new roll-up, a skip, or a new failure. */
function AnalyzeNow({ trace }: { trace: TraceDetail }) {
  const { session, failed_reason } = trace.analysis;
  const [requested, setRequested] = useState<{
    analyzedAt: string | null;
    failedReason: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const settled =
    requested !== null &&
    (session.status === "skipped" ||
      (session.status === "final" && session.analyzed_at !== requested.analyzedAt) ||
      (failed_reason !== null && failed_reason !== requested.failedReason));
  useEffect(() => {
    if (settled) setRequested(null);
  }, [settled]);

  const offered =
    session.status === "pending" || session.status === "in_progress" || failed_reason !== null;
  if (!offered && requested === null) return null;

  async function onAnalyze() {
    setError(null);
    setRequested({ analyzedAt: session.analyzed_at, failedReason: failed_reason });
    try {
      await analyzeTrace(trace.trace_id);
    } catch (err) {
      setRequested(null);
      setError(errorText(err, "Could not start the analysis — try again."));
    }
  }

  const running = requested !== null && !settled;
  return (
    <span className="inline-flex items-center gap-2">
      {error && <span className="text-xs text-error-deep">{error}</span>}
      <Button size="sm" variant="outline" disabled={running} onClick={onAnalyze}>
        <BusyLabel busy={running}>
          {!running && <Play data-slot="icon" />}
          {running ? "Analyzing…" : "Analyze now"}
        </BusyLabel>
      </Button>
    </span>
  );
}

function TurnRow({
  traceId,
  turn,
  isOwner,
  focused,
  onShowSpan,
  onAnalysisChange,
}: {
  traceId: string;
  turn: TurnAnalysis;
  isOwner: boolean;
  focused: boolean;
  onShowSpan: (sourceSpanId: string) => void;
  onAnalysisChange: (analysis: TraceAnalysis) => void;
}) {
  const categories = turn.labels.filter((l) => l.field === "task_category");
  const failures = turn.labels.filter((l) => l.field === "failure_mode");

  return (
    <li
      id={`turn-${turn.turn_index}`}
      className={cn("flex flex-col gap-1.5 py-2.5", focused && "-mx-2 rounded-md bg-secondary px-2")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">Turn {turn.turn_index + 1}</span>
        {turn.outcome ? (
          <OutcomeBadge outcome={turn.outcome} />
        ) : (
          <span className="text-xs text-muted-foreground">not judged</span>
        )}
        {turn.provenance === "human" && (
          <span
            className="inline-flex items-center gap-1 text-xs text-muted-foreground"
            title="Labeled by the owner; never re-judged"
          >
            <UserCheck className="size-3" /> human
          </span>
        )}
        {isOwner && (
          <span className="ml-auto">
            <RelabelTurn traceId={traceId} turn={turn} onSaved={onAnalysisChange} />
          </span>
        )}
      </div>
      {turn.uncertain && (
        <p className="flex items-start gap-1.5 text-xs text-warning-deep">
          <CircleHelp className="mt-px size-3 shrink-0" />
          <span>Uncertain: {turn.uncertain}</span>
        </p>
      )}
      {turn.summary && <p className="text-sm">{turn.summary}</p>}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {categories.map((label) => (
            <LabelChip key={label.value} field="task_category" value={label.value} />
          ))}
        </div>
      )}
      {failures.length > 0 && (
        <ul className="flex flex-col gap-1">
          {failures.map((label) => (
            <li key={label.value} className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
              <LabelChip
                field="failure_mode"
                value={label.value}
                title={label.span_ids.length > 0 ? "Show the evidence span" : undefined}
                onClick={
                  label.span_ids.length > 0 ? () => onShowSpan(label.span_ids[0]) : undefined
                }
              />
              {label.reason && (
                <span className="text-xs text-muted-foreground">{label.reason}</span>
              )}
              {label.span_ids.length > 1 &&
                label.span_ids.map((id, i) => (
                  <button
                    key={id}
                    type="button"
                    title={id}
                    onClick={() => onShowSpan(id)}
                    className="font-mono text-xs text-link-deep hover:underline"
                  >
                    span {i + 1}
                  </button>
                ))}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
