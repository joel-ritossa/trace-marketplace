"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, BellPlus, ExternalLink, Loader2, Sparkles, X } from "lucide-react";

import { AnalysisSection } from "@/components/traces/analysis-section";
import { TraceOutcome, VisibilityBadge } from "@/components/traces/badges";
import { TraceEvidence } from "@/components/traces/trace-evidence";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { ApiError } from "@/lib/api/client";
import {
  createSubscription,
  type Subscription,
  type SubscriptionAnchor,
} from "@/lib/api/subscriptions";
import {
  getSimilarTraces,
  type SimilarTraceItem,
  type SimilarTraces,
  type TraceDetail,
} from "@/lib/api/traces";
import { formatDuration } from "@/lib/format";

/** "Similar behavior" header action (docs/proposals/similar-behavior.md):
 *  opens a modal of cosine neighbors over the analysis-rendering embedding,
 *  with in-modal drill-down and a subscribe-to-this-behavior flow. */
export function SimilarBehaviorButton({ trace }: { trace: TraceDetail }) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<SimilarTraceItem | null>(null);

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setView(null);
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Sparkles /> Similar behavior
      </Button>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-3xl">
          {view === null ? (
            <SimilarList anchor={trace} onSelect={setView} />
          ) : (
            <SimilarDetail item={view} onBack={() => setView(null)} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

type LoadState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; result: SimilarTraces };

function SimilarList({
  anchor,
  onSelect,
}: {
  anchor: TraceDetail;
  onSelect: (item: SimilarTraceItem) => void;
}) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });

  useEffect(() => {
    let cancelled = false;
    getSimilarTraces(anchor.trace_id, { limit: 20 })
      .then((result) => !cancelled && setState({ phase: "ready", result }))
      .catch((err) =>
        setState({
          phase: "error",
          message: err instanceof ApiError ? err.message : "Could not load similar traces.",
        }),
      );
    return () => {
      cancelled = true;
    };
  }, [anchor.trace_id]);

  return (
    <>
      <DialogHeader>
        <DialogTitle>Similar behavior</DialogTitle>
        <DialogDescription>
          Traces whose behavior reads closest to “{anchor.name}” — ranked by embedding
          similarity over the analysis rendering, across your traces and the marketplace.
        </DialogDescription>
      </DialogHeader>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {state.phase === "loading" && (
          <p className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Finding similar traces…
          </p>
        )}
        {state.phase === "error" && <p className="py-4 text-sm text-error-deep">{state.message}</p>}
        {state.phase === "ready" && !state.result.anchor_embedded && (
          <p className="py-4 text-sm text-muted-foreground">
            This trace hasn’t been embedded yet — similarity needs a completed LLM analysis
            run (private traces require “allow LLM analysis” in settings).
          </p>
        )}
        {state.phase === "ready" && state.result.anchor_embedded && (
          <>
            {state.result.items.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                No other embedded traces to compare against yet.
              </p>
            ) : (
              <ul className="flex flex-col divide-y">
                {state.result.items.map((item) => (
                  <li key={item.trace_id}>
                    <button
                      type="button"
                      onClick={() => onSelect(item)}
                      className="flex w-full items-center gap-3 px-1 py-2.5 text-left transition-colors hover:bg-secondary/50"
                    >
                      <SimilarityDial value={item.similarity} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium">{item.name}</span>
                          {item.is_owner ? (
                            <VisibilityBadge visibility={item.visibility} />
                          ) : (
                            <span className="shrink-0 text-xs text-muted-foreground">
                              {item.owner_display_name ?? "marketplace"}
                            </span>
                          )}
                        </span>
                        <span className="mt-0.5 block truncate font-mono text-xs text-muted-foreground">
                          {[
                            item.provider,
                            item.model,
                            formatDuration(item.duration_ms),
                            `${item.span_count} spans`,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      <TraceOutcome trace={item} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {state.phase === "ready" && state.result.anchor_embedded && (
        <SubscribeToBehavior anchor={anchor} />
      )}
    </>
  );
}

function SimilarityDial({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <span className="flex w-12 shrink-0 flex-col items-center gap-1" title={value.toFixed(3)}>
      <span className="font-mono text-xs font-medium">{pct}%</span>
      <span className="h-1 w-full overflow-hidden rounded-full bg-secondary">
        <span
          className="block h-full rounded-full bg-foreground/70"
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </span>
    </span>
  );
}

function SimilarDetail({ item, onBack }: { item: SimilarTraceItem; onBack: () => void }) {
  return (
    <>
      <DialogHeader>
        <div className="flex items-center gap-2 pr-6">
          <Button size="icon-sm" variant="ghost" aria-label="Back to results" onClick={onBack}>
            <ArrowLeft />
          </Button>
          <DialogTitle className="min-w-0 flex-1 truncate">{item.name}</DialogTitle>
          <Button asChild size="sm" variant="outline">
            <Link href={`/traces/${item.trace_id}`}>
              <ExternalLink /> Full page
            </Link>
          </Button>
        </div>
        <DialogDescription>
          {Math.round(item.similarity * 100)}% behavior similarity
          {item.owner_display_name && !item.is_owner ? ` · by ${item.owner_display_name}` : ""}
        </DialogDescription>
      </DialogHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-lg border bg-background px-4 py-3 text-sm sm:grid-cols-4">
            {(
              [
                ["Duration", formatDuration(item.duration_ms)],
                ["Spans", String(item.span_count)],
                ["Errors", String(item.error_count)],
                ["Model", item.model ?? "—"],
              ] as [string, string][]
            ).map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="truncate font-mono text-xs" title={value}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          <AnalysisSection traceId={item.trace_id} isOwner={item.is_owner} />
          <TraceEvidence traceId={item.trace_id} />
        </div>
      </div>
    </>
  );
}

/** A subscription's behavior anchor, rendered beside its filter chips:
 *  read-only on list rows, editable (threshold slider + remove) on the feed
 *  page. A deleted anchor trace renders honestly — it matches nothing. */
export function BehaviorAnchor({
  sub,
  onPatch,
}: {
  sub: Subscription;
  onPatch?: (anchor: SubscriptionAnchor | null) => void;
}) {
  const [threshold, setThreshold] = useState(sub.similarity_threshold ?? DEFAULT_THRESHOLD);
  if (sub.similarity_threshold === null && sub.similar_to_trace_id === null) return null;

  if (sub.similar_to_trace_id === null) {
    return (
      <p className="text-xs text-error-deep">
        The anchor trace was deleted — this subscription matches nothing until the behavior
        anchor is removed or the subscription is recreated from another trace.
        {onPatch && (
          <button type="button" onClick={() => onPatch(null)} className="ml-1 font-medium underline">
            Remove anchor
          </button>
        )}
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1 rounded-full border bg-secondary px-2 py-0.5 font-mono text-xs text-foreground">
        <Sparkles className="size-3" />
        behaves like{" "}
        <Link href={`/traces/${sub.similar_to_trace_id}`} className="max-w-48 truncate underline">
          {sub.similar_to_name ?? sub.similar_to_trace_id.slice(0, 8)}
        </Link>
        · ≥ {Math.round(threshold * 100)}%
        {onPatch && (
          <button
            type="button"
            aria-label="Remove behavior anchor"
            onClick={() => onPatch(null)}
            className="-mr-0.5 rounded-full p-0.5 text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        )}
      </span>
      {onPatch && (
        <Slider
          value={[threshold]}
          onValueChange={([value]) => setThreshold(value)}
          onValueCommit={([value]) =>
            onPatch({ traceId: sub.similar_to_trace_id as string, threshold: value })
          }
          min={0.5}
          max={0.95}
          step={0.01}
          className="w-36"
          aria-label="Similarity threshold"
        />
      )}
    </div>
  );
}

const DEFAULT_THRESHOLD = 0.8;

/** Threshold slider with a live count of currently-matching visible traces
 *  — the calibration for what a behavior-anchored subscription would catch. */
function SubscribeToBehavior({ anchor }: { anchor: TraceDetail }) {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState(`Behaves like: ${anchor.name}`.slice(0, 120));
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);
  const [matching, setMatching] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const probeTicket = useRef(0);

  const probe = useCallback(
    (value: number) => {
      const ticket = ++probeTicket.current;
      getSimilarTraces(anchor.trace_id, { limit: 1, minSimilarity: value })
        .then((res) => {
          if (ticket === probeTicket.current) setMatching(res.total_above);
        })
        .catch(() => {});
    },
    [anchor.trace_id],
  );

  useEffect(() => {
    if (!expanded) return;
    const timer = setTimeout(() => probe(threshold), 250);
    return () => clearTimeout(timer);
  }, [expanded, threshold, probe]);

  async function onCreate() {
    setBusy(true);
    setError(null);
    try {
      const sub = await createSubscription(name.trim(), {}, {
        traceId: anchor.trace_id,
        threshold,
      });
      setCreatedId(sub.subscription_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the subscription.");
    } finally {
      setBusy(false);
    }
  }

  if (createdId !== null) {
    return (
      <p className="border-t pt-3 text-sm text-muted-foreground">
        Subscribed — you’ll be notified when a newly listed trace behaves like this one.{" "}
        <Link href={`/subscriptions/${createdId}`} className="font-medium underline">
          View subscription
        </Link>
      </p>
    );
  }

  if (!expanded) {
    return (
      <div className="border-t pt-3">
        <Button size="sm" variant="outline" onClick={() => setExpanded(true)}>
          <BellPlus /> Subscribe to this behavior
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 border-t pt-3">
      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        maxLength={120}
        placeholder="Subscription name"
        className="h-8 text-sm"
      />
      <div className="flex items-center gap-3">
        <span className="shrink-0 text-xs text-muted-foreground">Similarity ≥</span>
        <Slider
          value={[threshold]}
          onValueChange={([value]) => setThreshold(value)}
          min={0.5}
          max={0.95}
          step={0.01}
          className="max-w-56"
        />
        <span className="w-10 shrink-0 font-mono text-xs font-medium">
          {Math.round(threshold * 100)}%
        </span>
        <span className="text-xs text-muted-foreground">
          {matching === null ? "…" : `${matching} visible trace${matching === 1 ? "" : "s"} match now`}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" disabled={busy || name.trim().length === 0} onClick={onCreate}>
          {busy ? <Loader2 className="animate-spin" /> : <BellPlus />} Subscribe
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setExpanded(false)}>
          Cancel
        </Button>
        <span className="text-xs text-muted-foreground">
          Notifies on newly listed traces above the threshold.
        </span>
      </div>
      {error && <p className="text-xs text-error-deep">{error}</p>}
    </div>
  );
}
