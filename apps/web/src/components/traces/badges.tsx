import { describe, humanize } from "@/components/review/taxonomy";
import type { AnalysisStatus, Outcome, SkipReason, TraceVisibility } from "@/lib/api/traces";
import { cn } from "@/lib/utils";
import { BookMarked, CircleHelp, Globe, Loader2, Lock } from "lucide-react";
import Link from "next/link";
import type React from "react";

// The shared pill chrome (DESIGN.md badge-secondary geometry) every badge
// here builds on; tone classes add the status palette.
export const BADGE =
  "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium";
// badge-secondary: canvas-soft-2 fill with body-tone text (ink at reduced
// strength — mute on canvas-soft-2 is too faint in light).
export const NEUTRAL = "bg-secondary text-foreground/75";

/** Visibility is always visible (4_pages.md): every trace rendering carries one. */
export function VisibilityBadge({ visibility }: { visibility: TraceVisibility }) {
  const listed = visibility === "listed";
  return (
    <span
      className={cn(
        BADGE,
        listed ? "bg-link-soft text-link-deep" : NEUTRAL,
      )}
    >
      {listed ? <Globe className="size-3" /> : <Lock className="size-3" />}
      {visibility}
    </span>
  );
}

/** The importing agent (claude / codex / cursor) as a quiet mono tag, in
 *  place of the "claude:" name prefix. */
export function AgentBadge({ agent }: { agent: string }) {
  return <span className={cn(BADGE, NEUTRAL, "font-mono font-normal")}>{agent}</span>;
}

export function LibraryBadge() {
  return (
    <span className={cn(BADGE, OK_TONE)}>
      <BookMarked className="size-3" />
      saved
    </span>
  );
}

// Status palette soft fills with deep text; ok has no deep token, so light
// uses ink on the mint fill (status-ok on it is ~2:1).
const OK_TONE = "bg-status-ok-soft text-foreground dark:text-status-ok";
// partial takes the status palette's attention tone (DESIGN.md warning).
const OUTCOME_STYLE: Record<Outcome, string> = {
  success: OK_TONE,
  partial: "bg-warning-soft text-warning-deep",
  failure: "bg-error-soft text-error-deep",
  indeterminate: NEUTRAL,
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return (
    <span className={cn(BADGE, OUTCOME_STYLE[outcome])}>
      {humanize(outcome)}
    </span>
  );
}

/** One label value as a chip: task categories quiet, failure modes in the
 *  error tone. A button when clickable (an `onClick`, or as a popover
 *  trigger via `asChild`); otherwise a static span with no hover state. */
export function LabelChip({
  field,
  value,
  className,
  ...props
}: {
  field: "task_category" | "failure_mode";
  value: string;
} & React.ComponentProps<"button">) {
  const interactive = props.onClick !== undefined;
  const classes = cn(
    BADGE,
    "bg-secondary font-normal",
    field === "failure_mode" ? "text-error-deep" : "text-foreground/75",
    interactive &&
      "transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none data-[state=open]:ring-1 data-[state=open]:ring-border",
    interactive && (field === "failure_mode" ? "hover:bg-error-soft" : "hover:bg-accent"),
    className,
  );
  const label = <span className="truncate">{humanize(value)}</span>;
  return interactive ? (
    <button type="button" {...props} className={classes}>
      {label}
    </button>
  ) : (
    <span title={props.title ?? describe(value) ?? humanize(value)} className={classes}>
      {label}
    </span>
  );
}

export const SKIP_REASON_COPY: Record<SkipReason, string> = {
  not_configured: "Judge not configured",
  owner_opt_out: "LLM analysis is off for your private traces",
};

const STATUS_HELP: Record<AnalysisStatus, string> = {
  pending: "No turns judged yet — each turn is judged once the next one starts.",
  in_progress: "Some turns are judged; the session verdict comes once the session goes idle.",
  skipped: "LLM analysis was skipped; deterministic signals are still computed.",
  final: "The roll-up produced no session verdict.",
};

const STATUS_COPY: Record<AnalysisStatus, string> = {
  // Short: it sits in the Analysis column and beside the trace title.
  pending: "pending",
  in_progress: "analyzing",
  skipped: "skipped",
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
  const tone = failed
    ? "text-error-deep"
    : placeholder && status !== "skipped"
      ? "text-muted-foreground/60"
      : "text-foreground/75";
  const copy = failed
    ? "analysis failed"
    : placeholder && status !== "skipped"
      ? "not analyzed"
      : STATUS_COPY[status];
  return (
    <span
      className={cn(BADGE, "bg-secondary font-normal", tone)}
      title={
        failed
          ? "The last analysis run failed and will not retry on its own."
          : status === "skipped" && skipReason
            ? SKIP_REASON_COPY[skipReason]
            : STATUS_HELP[status]
      }
    >
      {!failed && !placeholder && status === "in_progress" && (
        <Loader2 className="size-3 animate-spin" />
      )}
      {copy}
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
      className="inline-flex shrink-0 items-center gap-1 text-xs text-link-deep hover:underline"
      title="The judge was uncertain about some turns — review to improve this trace's labels"
    >
      <CircleHelp className="size-3" />
      review
    </Link>
  );
}
