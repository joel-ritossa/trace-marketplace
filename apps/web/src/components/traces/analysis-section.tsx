"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CircleHelp, Tags } from "lucide-react";
import { OutcomeBadge, SKIP_REASON_COPY } from "@/components/traces/badges";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { createReviewItem } from "@/lib/api/review";
import { useRealtimeRefetch } from "@/lib/realtime";
import {
  getTraceAnalysis,
  type LabelValue,
  type TraceAnalysis,
  type Outcome,
} from "@/lib/api/traces";

type LoadState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; analysis: TraceAnalysis };

const SIGNAL_LABELS: [keyof NonNullable<TraceAnalysis["signals"]>, string][] = [
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

function LabelRow({ name, label }: { name: string; label: LabelValue | null }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{name}</dt>
      <dd className="mt-0.5 text-sm">
        {label ? (
          name === "Outcome" ? (
            <OutcomeBadge
              outcome={label.value as Outcome}
              confidence={label.confidence}
              provenance={label.provenance}
            />
          ) : (
            <span className="inline-flex items-center gap-1.5">
              <span className="font-medium">{label.value.replaceAll("_", " ")}</span>
              {label.confidence !== null && (
                <span className="font-mono text-xs text-muted-foreground">
                  {label.confidence.toFixed(2)}
                </span>
              )}
            </span>
          )
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
        {label && (
          <span className="ml-1.5 text-xs text-muted-foreground">{label.provenance}</span>
        )}
      </dd>
    </div>
  );
}

/** The trace-detail Analysis section (4_pages.md): labels → reasoning →
 *  signals → metric scores, audit behind a disclosure. Always renders, with
 *  the four honest states — never a lie. */
export function AnalysisSection({ traceId, isOwner }: { traceId: string; isOwner: boolean }) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const loadTicket = useRef(0);

  const load = useCallback(async () => {
    const ticket = ++loadTicket.current;
    try {
      const analysis = await getTraceAnalysis(traceId);
      if (ticket === loadTicket.current) setState({ phase: "ready", analysis });
    } catch (err) {
      if (ticket !== loadTicket.current) return;
      // A failed background refetch must not blank a rendered analysis.
      setState((prev) =>
        prev.phase === "ready"
          ? prev
          : {
              phase: "error",
              message: err instanceof ApiError ? err.message : "Could not load the analysis.",
            },
      );
    }
  }, [traceId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Live invalidation: the verdict row lands via "trace_analysis"; "traces"
  // catches state flips the row itself can't signal (attempts, re-ingest).
  useRealtimeRefetch("trace_analysis", load);
  useRealtimeRefetch("traces", load);

  return (
    <section className="rounded-lg border bg-background px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold">Analysis</h2>
        {state.phase === "ready" && isOwner && (
          <RelabelEntry traceId={traceId} analysis={state.analysis} />
        )}
      </div>
      <div className="mt-3">
        {state.phase === "loading" && (
          <p className="text-sm text-muted-foreground">Loading analysis…</p>
        )}
        {state.phase === "error" && <p className="text-sm text-error-deep">{state.message}</p>}
        {state.phase === "ready" && <Body analysis={state.analysis} isOwner={isOwner} />}
      </div>
    </section>
  );
}

/** Owner-initiated relabel entry (4_pages.md): routes to the resolve view —
 *  an open item links straight there, otherwise one is self-created. Only
 *  offered once analysis exists (the resolve path writes into its row). */
function RelabelEntry({ traceId, analysis }: { traceId: string; analysis: TraceAnalysis }) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [failed, setFailed] = useState(false);

  if (analysis.open_review_item_id !== null) {
    return (
      <Link
        href={`/review/${analysis.open_review_item_id}`}
        className="inline-flex items-center gap-1 text-xs text-link-deep hover:underline"
      >
        <CircleHelp className="size-3" /> open review item
      </Link>
    );
  }
  if (analysis.analysis_state !== "complete" && analysis.analysis_state !== "skipped") {
    return null;
  }
  return (
    <span className="inline-flex items-center gap-2">
      {failed && <span className="text-xs text-error-deep">could not start — try again</span>}
      <Button
        size="sm"
        variant="ghost"
        disabled={creating}
        className="h-7 px-2 text-xs text-muted-foreground"
        onClick={async () => {
          setCreating(true);
          setFailed(false);
          try {
            const item = await createReviewItem(traceId);
            router.push(`/review/${item.review_item_id}`);
          } catch {
            setFailed(true);
            setCreating(false);
          }
        }}
      >
        <Tags data-slot="icon" /> Relabel
      </Button>
    </span>
  );
}

function Body({ analysis, isOwner }: { analysis: TraceAnalysis; isOwner: boolean }) {
  if (analysis.analysis_state === "pending") {
    return <p className="text-sm text-muted-foreground">Analysis pending.</p>;
  }
  if (analysis.analysis_state === "failed") {
    return (
      <div>
        <p className="text-sm font-medium text-error-deep">Analysis failed</p>
        {analysis.failed_reason && (
          <p className="mt-1 font-mono text-xs text-muted-foreground">{analysis.failed_reason}</p>
        )}
      </div>
    );
  }

  const skipped = analysis.analysis_state === "skipped";
  // Human-provenance labels survive a machine rewrite even when the LLM
  // skipped (relabel → re-ingest on a keyless stack), so the grid renders
  // whenever any label exists — matching the list badge.
  const hasLabels =
    analysis.labels.outcome !== null ||
    analysis.labels.failure_mode !== null ||
    analysis.labels.task_category !== null;
  return (
    <div className="flex flex-col gap-4">
      {skipped && analysis.skip_reason && (
        <p className="text-sm text-muted-foreground">
          {SKIP_REASON_COPY[analysis.skip_reason]}
          {analysis.skip_reason === "owner_opt_out" && isOwner && (
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

      {(!skipped || hasLabels) && (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-3">
          <LabelRow name="Outcome" label={analysis.labels.outcome} />
          <LabelRow name="Failure mode" label={analysis.labels.failure_mode} />
          <LabelRow name="Task category" label={analysis.labels.task_category} />
        </dl>
      )}

      {analysis.reasoning && (
        <div>
          <h3 className="text-xs text-muted-foreground">Judge reasoning</h3>
          <p className="mt-1 text-sm">{analysis.reasoning}</p>
        </div>
      )}

      {analysis.signals && (
        <div>
          <h3 className="text-xs text-muted-foreground">Signals</h3>
          <dl className="mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
            {SIGNAL_LABELS.map(([key, label]) => (
              <div key={key} className="flex items-baseline justify-between gap-2 sm:block">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="font-mono text-xs">{formatSignal(analysis.signals![key])}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {analysis.metric_scores && Object.keys(analysis.metric_scores).length > 0 && (
        <div>
          <h3 className="text-xs text-muted-foreground">Metric scores</h3>
          <dl className="mt-1 grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
            {Object.entries(analysis.metric_scores).map(([name, value]) => (
              <div key={name} className="flex items-baseline justify-between gap-2 sm:block">
                <dt className="text-xs text-muted-foreground">{name}</dt>
                <dd className="font-mono text-xs">
                  {typeof value === "boolean" ? (value ? "yes" : "no") : value.toFixed(2)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {analysis.audit.analyzers.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            Audit details
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            {analysis.audit.analyzers.map((a) => (
              <div key={a.analyzer} className="rounded-md border px-3 py-2">
                <p className="font-mono text-xs">
                  {a.analyzer} · v{a.analyzer_version}
                  {a.model_id && ` · ${a.model_id}`}
                  {a.confidence !== null && ` · confidence ${a.confidence.toFixed(2)}`}
                  {a.rendering_truncated && " · rendering truncated"}
                </p>
                {a.votes && a.votes.length > 0 && (
                  <ul className="mt-1.5 flex flex-col gap-1">
                    {a.votes.map((vote, i) => (
                      <li key={i} className="font-mono text-xs text-muted-foreground">
                        {String(vote.call)} → {String(vote.value)}
                        {vote.reasoning ? ` — ${String(vote.reasoning)}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
