import type {
    AnalysisState,
    Outcome,
    Provenance,
    SkipReason,
    TraceVisibility,
} from "@/lib/api/traces";
import { cn } from "@/lib/utils";
import { BookMarked, CircleHelp, Globe, Lock } from "lucide-react";
import Link from "next/link";

/** Visibility is always visible (4_pages.md): every trace rendering carries one. */
export function VisibilityBadge({ visibility }: { visibility: TraceVisibility }) {
  const listed = visibility === "listed";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        listed ? "bg-link-soft text-link-deep" : "bg-secondary text-muted-foreground",
      )}
    >
      {listed ? <Globe className="size-3" /> : <Lock className="size-3" />}
      {visibility}
    </span>
  );
}

export function LibraryBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-status-ok-soft px-2 py-0.5 text-xs font-medium text-status-ok">
      <BookMarked className="size-3" />
      saved
    </span>
  );
}

const OUTCOME_SOLID: Record<Outcome, string> = {
  success: "bg-status-ok-soft text-status-ok",
  failure: "bg-error-soft text-error-deep",
  indeterminate: "bg-secondary text-muted-foreground",
};

const OUTCOME_OUTLINE: Record<Outcome, string> = {
  success: "border border-status-ok/50 text-status-ok",
  failure: "border border-error-deep/50 text-error-deep",
  indeterminate: "border border-border text-muted-foreground",
};

/** Outcome at list level (4_pages.md): variant encodes provenance — solid
 *  for human/human_confirmed, outline for machine — confidence as the raw
 *  number, never bucketed. */
export function OutcomeBadge({
  outcome,
  confidence,
  provenance,
}: {
  outcome: Outcome;
  confidence: number | null;
  provenance: Provenance | null;
}) {
  const human = provenance === "human" || provenance === "human_confirmed";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
        (human ? OUTCOME_SOLID : OUTCOME_OUTLINE)[outcome],
      )}
      title={provenance ? `provenance: ${provenance}` : undefined}
    >
      {outcome}
      {confidence !== null && <span className="font-mono opacity-70">{confidence.toFixed(2)}</span>}
    </span>
  );
}

export const SKIP_REASON_COPY: Record<SkipReason, string> = {
  not_configured: "Judge not configured",
  owner_opt_out: "LLM analysis is off for your private traces",
};

/** Non-verdict analysis states, quiet and honest (4_pages.md: never a lie,
 *  never alarm styling). `placeholder` is the no-row card rendering. */
export function AnalysisStateBadge({
  state,
  skipReason,
  placeholder = false,
}: {
  state: AnalysisState;
  skipReason?: SkipReason | null;
  placeholder?: boolean;
}) {
  if (state === "failed") {
    return <span className="text-xs text-error-deep">analysis failed</span>;
  }
  if (state === "skipped") {
    return (
      <span
        className="text-xs text-muted-foreground"
        title={skipReason ? SKIP_REASON_COPY[skipReason] : undefined}
      >
        analysis skipped
      </span>
    );
  }
  if (state === "pending" && !placeholder) {
    return <span className="text-xs text-muted-foreground">analysis pending</span>;
  }
  // Quiet placeholder, visually distinct from a verdict: also covers
  // complete-but-no-verdict (the judge failed open on every field).
  return <span className="text-xs text-muted-foreground/60">not analyzed</span>;
}

/** The needs-review indicator (4_pages.md /traces delta): links straight to
 *  the open review item. Owner-only data — non-owner rows never carry an id.
 *  Advisory framing: review improves labels, it gates nothing. */
export function NeedsReviewLink({ itemId }: { itemId: string }) {
  return (
    <Link
      href={`/review/${itemId}`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center gap-1 text-xs text-link-deep hover:underline"
      title="The judge was uncertain — review to improve this trace's labels"
    >
      <CircleHelp className="size-3" />
      review
    </Link>
  );
}

/** The one list-level analysis rendering (table cells and cards): outcome
 *  badge when a verdict exists, the honest state otherwise. */
export function TraceOutcome({
  trace,
  placeholder = false,
}: {
  trace: {
    outcome: Outcome | null;
    outcome_confidence: number | null;
    outcome_provenance: Provenance | null;
    analysis_state: AnalysisState;
  };
  placeholder?: boolean;
}) {
  if (trace.outcome) {
    return (
      <OutcomeBadge
        outcome={trace.outcome}
        confidence={trace.outcome_confidence}
        provenance={trace.outcome_provenance}
      />
    );
  }
  return <AnalysisStateBadge state={trace.analysis_state} placeholder={placeholder} />;
}
