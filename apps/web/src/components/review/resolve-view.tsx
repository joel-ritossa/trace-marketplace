"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { FAILURE_MODES, humanize, OUTCOMES, TASK_CATEGORIES } from "@/components/review/taxonomy";
import { TraceEvidence } from "@/components/traces/trace-evidence";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import {
  getReviewItem,
  listReviewItems,
  resolveReviewItem,
  type ResolvedLabel,
  type ReviewItem,
} from "@/lib/api/review";
import { getTraceAnalysis, type Outcome, type TraceAnalysis } from "@/lib/api/traces";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

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
 *  exactly when the reviewer most needs to see why. */
function judgeReasoning(analysis: TraceAnalysis): JudgeReasoning | null {
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
      <dt className="text-xs text-muted-foreground">{name}</dt>
      <dd className="mt-0.5 text-sm">
        {value !== null ? (
          <span className="inline-flex items-baseline gap-1.5">
            <span className="font-medium">{humanize(value)}</span>
            {confidence !== null && (
              <span className="font-mono text-xs text-muted-foreground">
                {confidence.toFixed(2)}
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
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
    <section className="rounded-lg border bg-background px-4 py-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {item.context.reasons.length > 0 ? "Why this is here" : "Machine verdict"}
      </h2>
      {item.context.reasons.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {item.context.reasons.map((reason) => (
            <li key={reason.code} className="text-sm">
              {reason.message}
            </li>
          ))}
        </ul>
      )}
      {item.context.reasons.length === 0 && (
        <p className="mt-2 text-sm text-muted-foreground">
          You asked to relabel this trace; the machine’s take is below for reference.
        </p>
      )}
      <dl className="mt-3 grid grid-cols-3 gap-x-4 gap-y-2 border-t pt-3">
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
        <div className="mt-3 border-t pt-3">
          <h3 className="text-xs text-muted-foreground">
            {reasoning.kind === "folded" ? "Judge reasoning" : "Judge votes (no consensus)"}
          </h3>
          {reasoning.kind === "folded" ? (
            <p className="mt-1 text-sm">{reasoning.text}</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-1.5">
              {reasoning.votes.map((vote, i) => (
                <li key={i} className="text-sm">
                  <span className="font-mono text-xs text-muted-foreground">{vote.value}</span>{" "}
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
    <dl className="grid grid-cols-1 gap-2">
      {Object.entries(labels).map(([field, label]) => (
        <div key={field} className="flex items-baseline justify-between gap-2">
          <dt className="text-xs text-muted-foreground">{humanize(field)}</dt>
          <dd className="text-sm">
            <span className="font-medium">{humanize(label.value)}</span>
            <span className="ml-1.5 font-mono text-xs text-muted-foreground">
              {label.confidence.toFixed(2)} · {label.provenance}
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

const UNANSWERED = "__unanswered__";

export function ResolveView({ itemId }: { itemId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const uploadFilter = searchParams.get("upload_id");

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
  // snapshot — fetched separately so the reviewer sees why the machine was
  // uncertain. Fails open: the card just omits it.
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

  // "Resolve & next" walks the queue under the current filter, newest first.
  const findNext = useCallback(() => {
    listReviewItems({ status: "open", uploadId: uploadFilter ?? undefined, limit: 2 })
      .then((res) => {
        const next = res.items.find((i) => i.review_item_id !== itemId);
        setNextId(next?.review_item_id ?? null);
      })
      .catch(() => setNextId(null));
  }, [itemId, uploadFilter]);

  useEffect(findNext, [findNext]);

  if (state.phase === "loading") {
    return <p className="text-sm text-muted-foreground">Loading review item…</p>;
  }
  if (state.phase === "not-found") {
    return (
      <div>
        <p className="text-sm font-medium">Review item not found</p>
        <p className="mt-1 text-sm text-muted-foreground">
          It may belong to a trace that was deleted, or the link is wrong.
        </p>
        <Button asChild size="sm" variant="outline" className="mt-4">
          <Link href="/review">
            <ArrowLeft /> Back to the queue
          </Link>
        </Button>
      </div>
    );
  }
  if (state.phase === "error") {
    return <p className="text-sm text-error-deep">{state.message}</p>;
  }

  const { item } = state;
  const queueHref = uploadFilter ? `/review?upload_id=${uploadFilter}` : "/review";
  const nextHref =
    nextId !== null
      ? uploadFilter
        ? `/review/${nextId}?upload_id=${uploadFilter}`
        : `/review/${nextId}`
      : null;

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
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href={queueHref}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3" /> Review queue
        </Link>
        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="min-w-0 truncate text-2xl font-semibold tracking-tight">
            {item.trace.name}
          </h1>
          <Link
            href={`/traces/${item.trace_id}`}
            className="text-xs text-muted-foreground underline hover:text-foreground"
          >
            open trace page
          </Link>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          From upload {item.upload_filename} · {formatDate(item.created_at)}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <TraceEvidence traceId={item.trace_id} className="h-[calc(100vh-18rem)]" />
        </div>

        <div className="flex flex-col gap-4">
          <MachineContext item={item} reasoning={reasoning} />

          {item.status !== "open" && !justResolved ? (
            <section className="rounded-lg border bg-background px-4 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {item.status === "resolved" ? "Resolved" : "Superseded"}
              </h2>
              {item.status === "resolved" ? (
                <>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Resolved by you{item.resolved_at ? ` on ${formatDate(item.resolved_at)}` : ""}.
                    Answered fields carry human provenance and confidence 1.00.
                  </p>
                  {item.answer && (
                    <dl className="mt-3 grid grid-cols-1 gap-1.5 border-t pt-3">
                      {(["outcome", "failure_mode", "task_category"] as const).map(
                        (field) =>
                          item.answer?.[field] && (
                            <div key={field} className="flex items-baseline justify-between">
                              <dt className="text-xs text-muted-foreground">{humanize(field)}</dt>
                              <dd className="text-sm font-medium">
                                {humanize(item.answer[field]!)}
                              </dd>
                            </div>
                          ),
                      )}
                    </dl>
                  )}
                </>
              ) : (
                <p className="mt-2 text-sm text-muted-foreground">
                  A newer analysis run superseded this item. If it routed again, the fresh item is
                  in the <Link href={queueHref} className="underline">queue</Link>.
                </p>
              )}
            </section>
          ) : justResolved ? (
            <section className="rounded-lg border bg-background px-4 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-status-ok">
                Resolved
              </h2>
              <div className="mt-3">
                <ResolvedLabels labels={resolvedLabels} />
              </div>
              <div className="mt-4 flex gap-2">
                {nextHref !== null ? (
                  <Button asChild size="sm">
                    <Link href={nextHref}>
                      Next item <ArrowRight data-slot="icon" />
                    </Link>
                  </Button>
                ) : null}
                <Button asChild size="sm" variant={nextHref !== null ? "outline" : "default"}>
                  <Link href={queueHref}>Back to queue</Link>
                </Button>
              </div>
            </section>
          ) : (
            <section className="rounded-lg border bg-background px-4 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Your verdict
              </h2>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Answer any of the fields — partial resolutions are fine. Indeterminate is a valid
                answer, not a skip.
              </p>

              <div className="mt-3 flex flex-col gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Outcome</p>
                  <div className="mt-1.5 grid grid-cols-3 gap-1.5">
                    {OUTCOMES.map(({ value, description }) => (
                      <button
                        key={value}
                        type="button"
                        title={description}
                        onClick={() => pickOutcome(value)}
                        className={cn(
                          "rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                          outcome === value
                            ? "border-foreground bg-foreground text-background"
                            : "text-muted-foreground hover:bg-accent hover:text-foreground",
                        )}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </div>

                {outcome === "failure" && (
                  <div>
                    <p className="text-xs text-muted-foreground">Failure mode</p>
                    <Select
                      value={failureMode ?? UNANSWERED}
                      onValueChange={(v) => setFailureMode(v === UNANSWERED ? null : v)}
                    >
                      <SelectTrigger className="mt-1.5 w-full">
                        <SelectValue placeholder="Leave unanswered" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={UNANSWERED}>
                          <span className="text-muted-foreground">Leave unanswered</span>
                        </SelectItem>
                        {FAILURE_MODES.map(({ value, description }) => (
                          <SelectItem key={value} value={value}>
                            <span className="flex flex-col items-start">
                              <span>{humanize(value)}</span>
                              <span className="text-xs text-muted-foreground">{description}</span>
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                <div>
                  <p className="text-xs text-muted-foreground">Task category</p>
                  <Select
                    value={taskCategory ?? UNANSWERED}
                    onValueChange={(v) => setTaskCategory(v === UNANSWERED ? null : v)}
                  >
                    <SelectTrigger className="mt-1.5 w-full">
                      <SelectValue placeholder="Leave unanswered" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={UNANSWERED}>
                        <span className="text-muted-foreground">Leave unanswered</span>
                      </SelectItem>
                      {TASK_CATEGORIES.map((value) => (
                        <SelectItem key={value} value={value}>
                          {humanize(value)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {formError && <p className="text-sm text-error-deep">{formError}</p>}

                <div className="flex gap-2">
                  {nextHref !== null ? (
                    <Button
                      size="sm"
                      disabled={!answered || submitting}
                      onClick={async () => {
                        if (await onResolve()) router.push(nextHref);
                      }}
                    >
                      Resolve &amp; next <ArrowRight data-slot="icon" />
                    </Button>
                  ) : null}
                  <Button
                    size="sm"
                    variant={nextHref !== null ? "outline" : "default"}
                    disabled={!answered || submitting}
                    onClick={onResolve}
                  >
                    Resolve
                  </Button>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
