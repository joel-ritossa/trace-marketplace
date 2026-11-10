import { humanize } from "@/components/review/taxonomy";
import type { AnalysisStatus, Outcome, SkipReason, TraceVisibility } from "@/lib/api/traces";
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

// partial takes the status palette's attention tone (DESIGN.md warning).
const OUTCOME_STYLE: Record<Outcome, string> = {
  success: "bg-status-ok-soft text-status-ok",
  partial: "bg-warning-soft text-warning-deep",
  failure: "bg-error-soft text-error-deep",
  indeterminate: "bg-secondary text-muted-foreground",
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        OUTCOME_STYLE[outcome],
      )}
    >
      {outcome}
    </span>
  );
}

/** One label value as a chip: task categories quiet, failure modes in the
 *  error tone. Clickable when `onClick` is given (evidence links). */
export function LabelChip({
  field,
  value,
  title,
  onClick,
}: {
  field: "task_category" | "failure_mode";
  value: string;
  title?: string;
  onClick?: () => void;
}) {
  const className = cn(
    "inline-flex items-center rounded-full px-2 py-0.5 text-xs",
    field === "failure_mode"
      ? "border border-error-deep/50 text-error-deep"
      : "bg-secondary text-muted-foreground",
    onClick && "transition-colors hover:bg-error-soft",
  );
  return onClick ? (
    <button type="button" title={title} onClick={onClick} className={className}>
      {humanize(value)}
    </button>
  ) : (
    <span title={title} className={className}>
      {humanize(value)}
    </span>
  );
}

/** A session's (or turn's) label sets as chips; nothing when both are empty. */
export function LabelChips({
  taskCategories,
  failureModes,
  className,
}: {
  taskCategories: string[];
  failureModes: string[];
  className?: string;
}) {
  if (taskCategories.length === 0 && failureModes.length === 0) return null;
  return (
    <span className={cn("flex flex-wrap gap-1", className)}>
      {taskCategories.map((value) => (
        <LabelChip key={value} field="task_category" value={value} />
      ))}
      {failureModes.map((value) => (
        <LabelChip key={value} field="failure_mode" value={value} />
      ))}
    </span>
  );
}

export const SKIP_REASON_COPY: Record<SkipReason, string> = {
  not_configured: "Judge not configured",
  owner_opt_out: "LLM analysis is off for your private traces",
};

const STATUS_COPY: Record<AnalysisStatus, string> = {
  pending: "analysis pending",
  in_progress: "analysis in progress",
  skipped: "analysis skipped",
  // Final without a session outcome: the roll-up produced no verdict.
  final: "no verdict",
};

/** Non-verdict analysis states, quiet and honest (4_pages.md: never a lie,
 *  never alarm styling). `placeholder` is the no-verdict card rendering on
 *  other people's traces. */
export function AnalysisStatusBadge({
  status,
  failed,
  skipReason,
  placeholder = false,
}: {
  status: AnalysisStatus;
  failed: boolean;
  skipReason?: SkipReason | null;
  placeholder?: boolean;
}) {
  if (failed) {
    return <span className="text-xs text-error-deep">analysis failed</span>;
  }
  if (placeholder && status !== "skipped") {
    return <span className="text-xs text-muted-foreground/60">not analyzed</span>;
  }
  return (
    <span
      className="text-xs text-muted-foreground"
      title={status === "skipped" && skipReason ? SKIP_REASON_COPY[skipReason] : undefined}
    >
      {STATUS_COPY[status]}
    </span>
  );
}

/** The needs-review indicator (4_pages.md /traces delta): links to the
 *  trace, where the uncertain turns are marked and relabeled. Owner-only
 *  data. Advisory framing: review improves labels, it gates nothing. */
export function NeedsReviewLink({ traceId }: { traceId: string }) {
  return (
    <Link
      href={`/traces/${traceId}`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center gap-1 text-xs text-link-deep hover:underline"
      title="The judge was uncertain about some turns — review to improve this trace's labels"
    >
      <CircleHelp className="size-3" />
      review
    </Link>
  );
}

/** The one outcome rendering (table cells, cards, the detail header): the
 *  session outcome badge when a verdict exists, the honest state otherwise. */
export function TraceOutcome({
  outcome,
  status,
  failed,
  placeholder = false,
}: {
  outcome: Outcome | null;
  status: AnalysisStatus;
  failed: boolean;
  placeholder?: boolean;
}) {
  if (outcome) return <OutcomeBadge outcome={outcome} />;
  return <AnalysisStatusBadge status={status} failed={failed} placeholder={placeholder} />;
}
