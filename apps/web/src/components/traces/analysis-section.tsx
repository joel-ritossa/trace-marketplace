"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowDown,
  Bot,
  ChevronRight,
  CircleHelp,
  Play,
  Tags,
  TriangleAlert,
  UserCheck,
  X,
} from "lucide-react";
import { humanize } from "@/components/review/taxonomy";
import { SubagentIcon, subagentLine } from "@/components/traces/agents-view";
import { SKIP_REASON_COPY } from "@/components/traces/badges";
import {
  FailureCountPopover,
  LabelPill,
  LabelPopover,
  OutcomePill,
  SkillIcon,
  SkillPill,
  type TurnSource,
} from "@/components/traces/label-popovers";
import { BusyLabel } from "@/components/traces/bulk-bar";
import { RelabelTurn } from "@/components/traces/relabel-turn";
import { Button } from "@/components/ui/button";
import { ExpandableText } from "@/components/ui/expandable-text";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { errorText } from "@/lib/api/client";
import {
  analyzeTrace,
  type AnalysisSignals,
  type TraceAnalysis,
  type TraceDetail,
  type AgentSpawn,
  type SkillUse,
  type TurnAnalysis,
  type TurnLabel,
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

// Categories the session card shows before "Show all"; the session array is
// most-frequent first.
const SESSION_CATEGORY_PREVIEW = 6;

const labelsOf = (turn: TurnAnalysis, field: TurnLabel["field"]) =>
  turn.labels.filter((l) => l.field === field);

const findLabel = (turn: TurnAnalysis, field: TurnLabel["field"], value: string) =>
  turn.labels.find((l) => l.field === field && l.value === value);

type TurnFilterKey = "all" | "not_success" | "failures" | "uncertain";
export type TurnFilter = TurnFilterKey | { mode: string } | { skill: string };

const TURN_FILTERS: { key: TurnFilterKey; label: string; match: (t: TurnAnalysis) => boolean }[] =
  [
    { key: "all", label: "All", match: () => true },
    {
      key: "not_success",
      label: "Not success",
      match: (t) => t.outcome !== null && t.outcome !== "success",
    },
    { key: "failures", label: "Failure modes", match: (t) => labelsOf(t, "failure_mode").length > 0 },
    { key: "uncertain", label: "Uncertain", match: (t) => t.uncertain !== null },
  ];

function matches(turn: TurnAnalysis, filter: TurnFilter, skills: SkillUse[]): boolean {
  if (typeof filter === "object") {
    if ("skill" in filter)
      return skills.some((u) => u.name === filter.skill && u.turn_index === turn.turn_index);
    return !!findLabel(turn, "failure_mode", filter.mode);
  }
  return TURN_FILTERS.find((f) => f.key === filter)!.match(turn);
}

const MODE_PREFIX = "mode:";
const SKILL_PREFIX = "skill:";

function parseFilter(raw: string | null): TurnFilter {
  if (raw?.startsWith(MODE_PREFIX)) return { mode: raw.slice(MODE_PREFIX.length) };
  if (raw?.startsWith(SKILL_PREFIX)) return { skill: raw.slice(SKILL_PREFIX.length) };
  return TURN_FILTERS.find((f) => f.key === raw)?.key ?? "all";
}

function encodeFilter(filter: Exclude<TurnFilter, "all">): string {
  if (typeof filter === "string") return filter;
  return "skill" in filter ? SKILL_PREFIX + filter.skill : MODE_PREFIX + filter.mode;
}

/** The turn filter as `?turns=` on the trace page (URL carries view state,
 *  like the list filters); local state where the section is embedded. */
function useTurnFilter(syncUrl: boolean): [TurnFilter, (filter: TurnFilter) => void] {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [local, setLocal] = useState<TurnFilter>("all");
  if (!syncUrl) return [local, setLocal];
  return [
    parseFilter(searchParams.get("turns")),
    (filter) => {
      const params = new URLSearchParams(searchParams);
      if (filter === "all") params.delete("turns");
      else params.set("turns", encodeFilter(filter));
      router.replace(params.size > 0 ? `${pathname}?${params}` : pathname, { scroll: false });
    },
  ];
}

/** Moving around the section: reveal a turn (expand, highlight, scroll —
 *  the same as `?turn=N`), reveal an evidence span, narrow the turn list. */
export type Nav = {
  goToTurn: (turnIndex: number) => void;
  showSpan: (sourceSpanId: string) => void;
  // Narrow the turn list (failure mode / skill); absent outside the section.
  filterTurns?: (filter: TurnFilter) => void;
  // The evidence pane's Agents view (optionally at a turn's group), and
  // scoping it to one subagent; absent where there is no evidence pane.
  showAgents?: (turnIndex?: number) => void;
  openAgent?: (spanId: string) => void;
};

/** The trace-detail Analysis section (9_session-analysis.md): the session
 *  verdict card over one compact, expandable row per judged turn. Label
 *  pills open popovers that lead to their turns and evidence spans
 *  (`onShowSpan`, by source span id); owners relabel per turn. Always
 *  renders, with honest states — never a lie. */
export function AnalysisSection({
  trace,
  onChange,
  onShowSpan,
  focusTurn,
  turnRequest,
  onTurnSelected,
  syncUrl = false,
  className,
  agents,
  showAgents,
  openAgent,
  scoped = false,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
  onShowSpan: (sourceSpanId: string) => void;
  agents?: AgentSpawn[] | null;
  showAgents?: (turnIndex?: number) => void;
  openAgent?: (spanId: string) => void;
  // The evidence pane is scoped to a subagent.
  scoped?: boolean;
  focusTurn?: number;
  // "Go to turn" from outside the section (the span panels); seq re-fires.
  turnRequest?: { turnIndex: number; seq: number } | null;
  // A turn was explicitly selected here (expand, Next issue, a popover).
  onTurnSelected?: (turnIndex: number) => void;
  syncUrl?: boolean;
  className?: string;
}) {
  const { analysis } = trace;
  const onAnalysisChange = (next: TraceAnalysis) => onChange({ ...trace, analysis: next });
  const [filter, setFilter] = useTurnFilter(syncUrl);
  const skills = trace.skills ?? [];
  const [openTurns, setOpenTurns] = useState<ReadonlySet<number>>(
    () => new Set(focusTurn !== undefined ? [focusTurn] : []),
  );
  const [highlight, setHighlight] = useState(focusTurn);
  const [scrollTo, setScrollTo] = useState<{ turnIndex: number; seq: number } | null>(
    focusTurn !== undefined ? { turnIndex: focusTurn, seq: 0 } : null,
  );

  // Review links and "Go to turn" land on one turn: scroll it into view once
  // its row exists.
  const targetPresent = analysis.turns.some((t) => t.turn_index === scrollTo?.turnIndex);
  useEffect(() => {
    if (targetPresent && scrollTo) {
      document
        .getElementById(`turn-${scrollTo.turnIndex}`)
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [targetPresent, scrollTo]);

  function toggleTurn(turnIndex: number) {
    const opening = !openTurns.has(turnIndex);
    setOpenTurns((prev) => {
      const next = new Set(prev);
      if (!next.delete(turnIndex)) next.add(turnIndex);
      return next;
    });
    // Expanding a turn selects it (the evidence pane follows).
    if (opening) {
      setHighlight(turnIndex);
      onTurnSelected?.(turnIndex);
    }
  }

  function reveal(turnIndex: number) {
    const turn = analysis.turns.find((t) => t.turn_index === turnIndex);
    if (turn && !matches(turn, filter, skills)) setFilter("all");
    setOpenTurns((prev) => new Set(prev).add(turnIndex));
    setHighlight(turnIndex);
    setScrollTo((prev) => ({ turnIndex, seq: (prev?.seq ?? 0) + 1 }));
  }

  const nav: Nav = {
    goToTurn(turnIndex) {
      reveal(turnIndex);
      onTurnSelected?.(turnIndex);
    },
    showSpan: onShowSpan,
    filterTurns: setFilter,
    showAgents,
    openAgent,
  };

  useEffect(() => {
    // From outside: reveal only (the host already knows).
    if (turnRequest) reveal(turnRequest.turnIndex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turnRequest]);

  const shown = analysis.turns.filter((t) => matches(t, filter, skills));
  const issueTurns = analysis.turns.filter((t) => labelsOf(t, "failure_mode").length > 0);
  function nextIssue() {
    const next =
      issueTurns.find((t) => highlight === undefined || t.turn_index > highlight) ??
      issueTurns[0];
    if (next) nav.goToTurn(next.turn_index);
  }

  return (
    <section
      className={cn("flex flex-col gap-4 rounded-lg border bg-background px-4 py-3", className)}
    >
      {scoped && (
        <p className="text-xs text-muted-foreground">
          Viewing subagent — labels below are for the whole session.
        </p>
      )}
      <SessionCard trace={trace} nav={nav} agents={agents} />
      {analysis.turns.length > 0 && (
        <div>
          {/* Stays in view while the turns scroll under it. */}
          <div className="sticky -top-3 z-[1] -mx-4 flex flex-wrap items-center justify-between gap-2 border-b bg-background px-4 py-1.5">
            <h3 className="text-xs text-muted-foreground">
              Turns · <span className="font-mono">{analysis.turns.length}</span>
            </h3>
            <div className="flex flex-wrap items-center gap-1">
              <TurnFilterBar turns={analysis.turns} filter={filter} onChange={setFilter} />
              <Button
                size="xs"
                variant="ghost"
                disabled={issueTurns.length === 0}
                onClick={nextIssue}
                title="Expand and scroll to the next turn with a failure mode"
                className="text-muted-foreground"
              >
                <ArrowDown /> Next issue
              </Button>
            </div>
          </div>
          {/* Collapsed rows are one light line each; detail renders on expand. */}
          <ol className="mt-1 divide-y">
            {shown.map((turn) => (
              <TurnRow
                key={turn.turn_index}
                trace={trace}
                spawns={(agents ?? []).filter((a) => a.turn_index === turn.turn_index)}
                turn={turn}
                open={openTurns.has(turn.turn_index)}
                highlighted={turn.turn_index === highlight}
                onToggle={() => toggleTurn(turn.turn_index)}
                onExpand={() => setOpenTurns((prev) => new Set(prev).add(turn.turn_index))}
                nav={nav}
                onAnalysisChange={onAnalysisChange}
              />
            ))}
          </ol>
          {shown.length === 0 && (
            <p className="py-2 text-xs text-muted-foreground">No turns match this filter.</p>
          )}
        </div>
      )}
    </section>
  );
}

function TurnFilterBar({
  turns,
  filter,
  onChange,
}: {
  turns: TurnAnalysis[];
  filter: TurnFilter;
  onChange: (filter: TurnFilter) => void;
}) {
  return (
    <>
      {typeof filter === "object" && (
        <Button
          size="xs"
          variant="secondary"
          onClick={() => onChange("all")}
          aria-label={`Clear the ${"skill" in filter ? filter.skill : humanize(filter.mode)} filter`}
        >
          {"skill" in filter ? (
            <>
              <SkillIcon /> {filter.skill}
            </>
          ) : (
            humanize(filter.mode)
          )}
          <X />
        </Button>
      )}
      {TURN_FILTERS.map(({ key, label, match }) => {
        const count = turns.filter(match).length;
        const active = filter === key;
        return (
          <Button
            key={key}
            size="xs"
            variant={active ? "secondary" : "ghost"}
            disabled={count === 0 && key !== "all"}
            aria-pressed={active}
            onClick={() => onChange(key)}
            className={cn(!active && "text-muted-foreground")}
          >
            {label}
            <span className="font-mono">{count}</span>
          </Button>
        );
      })}
    </>
  );
}

/** Session / turn prose: clamped, expandable in place (shared primitive). */
export function ClampedText({ text, lines = 3 }: { text: string; lines?: 3 | 6 }) {
  return <ExpandableText text={text} lines={lines} className="mt-0.5 text-sm" />;
}

export function SessionCard({
  trace,
  nav,
  agents,
}: {
  trace: TraceDetail;
  nav: Nav;
  agents?: AgentSpawn[] | null;
}) {
  const { session, turns, failed_reason } = trace.analysis;
  const source = loadedSource(trace, nav);
  const judged = turns.filter((t) => t.outcome !== null).length;
  const uncertain = turns.filter((t) => t.uncertain !== null).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          Analysis
          {session.outcome && <OutcomePill outcome={session.outcome} source={source} />}
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
      {session.status === "in_progress" &&
        (session.outcome && session.analyzed_at ? (
          // A verdict exists but newer turns arrived after it.
          <p className="text-sm text-muted-foreground">
            Verdict from {formatDate(session.analyzed_at)}; newer turns since — it refreshes when
            the session goes idle.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {judged} of {plural(session.turn_count, "turn")} judged — the session verdict is
            written once the session goes idle.
          </p>
        ))}
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
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <CircleHelp className="size-3.5 shrink-0" />
          The judge was uncertain about {plural(uncertain, "turn")} — relabeling them improves this
          trace’s labels.
        </p>
      )}

      {session.goal && (
        <div>
          <h3 className="text-xs text-muted-foreground">Goal</h3>
          <ClampedText text={session.goal} />
        </div>
      )}
      {session.summary && (
        <div>
          <h3 className="text-xs text-muted-foreground">What happened</h3>
          <ClampedText text={session.summary} />
        </div>
      )}
      <SessionCategories values={session.task_categories} source={source} />
      <SessionFailureModes values={session.failure_modes} turns={turns} source={source} nav={nav} />
      <SessionSkills skills={trace.skills ?? []} source={source} nav={nav} />
      <SessionSubagents trace={trace} agents={agents} nav={nav} />

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

      {session.analyzed_at && session.status === "final" && (
        <p className="text-xs text-muted-foreground">
          Session verdict written {formatDate(session.analyzed_at)}
        </p>
      )}
    </div>
  );
}

/** The trace page's source for the shared pill popovers. */
export function loadedSource(trace: TraceDetail, nav: Nav): TurnSource {
  return {
    kind: "loaded",
    turns: trace.analysis.turns,
    session: trace.analysis.session,
    skills: trace.skills ?? [],
    goToTurn: nav.goToTurn,
    showSpan: nav.showSpan,
  };
}

function SessionCategories({ values, source }: { values: string[]; source: TurnSource }) {
  const [all, setAll] = useState(false);
  if (values.length === 0) return null;
  const hidden = values.length - SESSION_CATEGORY_PREVIEW;
  return (
    <div>
      <h3 className="text-xs text-muted-foreground">
        Task categories · <span className="font-mono">{values.length}</span>
      </h3>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {(all ? values : values.slice(0, SESSION_CATEGORY_PREVIEW)).map((value) => (
          <LabelPill key={value} field="task_category" value={value} source={source} />
        ))}
        {hidden > 0 && (
          <button
            type="button"
            onClick={() => setAll((v) => !v)}
            className="rounded-sm px-1 text-xs font-medium text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {all ? "Show less" : `Show all ${values.length}`}
          </button>
        )}
      </div>
    </div>
  );
}

/** "Show only these turns" under a popover, when the section can filter. */
function ShowOnly({ onClick }: { onClick?: () => void }) {
  if (!onClick) return null;
  return (
    <PopoverClose asChild>
      <Button size="xs" variant="ghost" className="mt-2 text-muted-foreground" onClick={onClick}>
        Show only these turns
      </Button>
    </PopoverClose>
  );
}

/** Session failure modes grouped with how many turns show each; each opens
 *  the shared label popover. */
function SessionFailureModes({
  values,
  turns,
  source,
  nav,
}: {
  values: string[];
  turns: TurnAnalysis[];
  source: TurnSource;
  nav: Nav;
}) {
  if (values.length === 0) return null;
  return (
    <div>
      <h3 className="text-xs text-muted-foreground">
        Failure modes · <span className="font-mono">{values.length}</span>
      </h3>
      <ul className="mt-1 flex flex-col">
        {values.map((value) => {
          const count = turns.filter((t) => findLabel(t, "failure_mode", value)).length;
          return (
            <li key={value}>
              <LabelPopover
                field="failure_mode"
                value={value}
                source={source}
                footer={
                  count > 1 && nav.filterTurns ? (
                    <ShowOnly onClick={() => nav.filterTurns?.({ mode: value })} />
                  ) : null
                }
              >
                <button
                  type="button"
                  className="-mx-1 flex w-[calc(100%+0.5rem)] items-center gap-2 rounded-md px-1 py-1 text-left transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none data-[state=open]:bg-accent/50"
                >
                  <TriangleAlert className="size-3 shrink-0 text-error-deep" />
                  <span className="min-w-0 flex-1 truncate text-sm">{humanize(value)}</span>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">
                    {plural(count, "turn")}
                  </span>
                </button>
              </LabelPopover>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Session facts: how the main agent fanned out, with a way to the layout. */
function SessionSubagents({
  trace,
  agents,
  nav,
}: {
  trace: TraceDetail;
  agents?: AgentSpawn[] | null;
  nav: Nav;
}) {
  const summary = trace.subagents;
  if (!summary || summary.count === 0) return null;
  return (
    <div>
      <h3 className="text-xs text-muted-foreground">
        Subagents · <span className="font-mono">{summary.count}</span>
      </h3>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm">
        <SubagentIcon className="size-3.5 text-muted-foreground" />
        {subagentLine(summary.count, summary.turns, agents ?? undefined)}
        {nav.showAgents && (
          <button
            type="button"
            onClick={() => nav.showAgents?.()}
            className="rounded-sm text-xs font-medium text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            View layout
          </button>
        )}
      </p>
    </div>
  );
}

/** Session facts, not judge labels: the skills used, each with its uses. */
function SessionSkills({ skills, source, nav }: { skills: SkillUse[]; source: TurnSource; nav: Nav }) {
  if (skills.length === 0) return null;
  const counts = new Map<string, number>();
  for (const use of skills) counts.set(use.name, (counts.get(use.name) ?? 0) + 1);
  return (
    <div>
      <h3 className="text-xs text-muted-foreground">
        Skills · <span className="font-mono">{counts.size}</span>
      </h3>
      <div className="mt-1 flex flex-wrap gap-1">
        {[...counts].map(([name, uses]) => (
          <SkillPill
            key={name}
            name={name}
            uses={uses}
            source={source}
            footer={
              nav.filterTurns ? () => <ShowOnly onClick={() => nav.filterTurns?.({ skill: name })} /> : undefined
            }
          />
        ))}
      </div>
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
          {running ? "Analyzing…" : session.outcome ? "Refresh verdict" : "Analyze now"}
        </BusyLabel>
      </Button>
    </span>
  );
}

// Turn origin (`turn.origin` on the turn span; absent = human). The analysis
// API may carry it per turn; read it optionally.
type TurnOrigin = "human" | "automated";
export const originOf = (turn: TurnAnalysis): TurnOrigin | undefined => turn.origin;

/** A subtle marker for turns started by automation (CI events), not a person. */
export function AutomatedMarker() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground"
      title="Started by an automated event (e.g. CI), not a person"
    >
      <Bot className="size-3" /> automated
    </span>
  );
}

/** One turn: a single scannable line (outcome, flags, summary) that expands
 *  to the reason, labels with their evidence, and the relabel action. */
function TurnRow({
  trace,
  spawns,
  turn,
  open,
  highlighted,
  onToggle,
  onExpand,
  nav,
  onAnalysisChange,
}: {
  trace: TraceDetail;
  spawns: AgentSpawn[];
  turn: TurnAnalysis;
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
  onExpand: () => void;
  nav: Nav;
  onAnalysisChange: (analysis: TraceAnalysis) => void;
}) {
  // Bumped by the uncertain popover's Relabel; reset on collapse so a later
  // expand doesn't reopen the dialog.
  const [relabelSignal, setRelabelSignal] = useState(0);
  const failures = labelsOf(turn, "failure_mode");
  const source = loadedSource(trace, nav);
  const skillNames = [...turnSkills(trace, turn).keys()];
  const toggle = () => {
    if (open) setRelabelSignal(0);
    onToggle();
  };

  return (
    <li
      id={`turn-${turn.turn_index}`}
      className={cn(
        "relative scroll-my-10 px-1",
        // DESIGN.md selected row: canvas-soft-2 fill + primary left edge.
        // (the fill stays on the summary line so chips below keep contrast).
        highlighted &&
          "before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-primary",
      )}
    >
      <div className={cn("flex items-center gap-2", highlighted && "rounded-sm bg-secondary")}>
        {/* The toggle owns the turn label and the summary; the pills between
            are their own controls (no buttons inside buttons). */}
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="-mx-1 flex shrink-0 items-center gap-2 rounded-md px-1 py-1.5 text-left transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <ChevronRight
            className={cn(
              "size-3 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
          <span className="w-14 shrink-0 font-mono text-xs text-muted-foreground">
            Turn {turn.turn_index + 1}
          </span>
        </button>
        {turn.outcome ? (
          <OutcomePill outcome={turn.outcome} source={source} turn={turn} />
        ) : (
          <span className="shrink-0 text-xs text-muted-foreground">not judged</span>
        )}
        <FailureCountPopover values={failures.map((l) => l.value)} source={source} />
        {originOf(turn) === "automated" && <AutomatedMarker />}
        {spawns.length > 0 && (
          <button
            type="button"
            onClick={() => nav.showAgents?.(turn.turn_index)}
            disabled={!nav.showAgents}
            title={`${spawns.length} subagent${spawns.length === 1 ? "" : "s"} — show the layout`}
            className="inline-flex shrink-0 items-center gap-0.5 rounded-sm font-mono text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <SubagentIcon className="size-3" />
            {spawns.length}
          </button>
        )}
        {skillNames.length > 0 && (
          <span
            className="shrink-0 text-muted-foreground"
            title={`Skills: ${skillNames.join(", ")}`}
            aria-label={`Skills: ${skillNames.join(", ")}`}
          >
            <SkillIcon className="size-3" />
          </span>
        )}
        <button
          type="button"
          tabIndex={-1}
          onClick={toggle}
          className="min-w-0 flex-1 truncate py-1.5 text-left text-sm"
        >
          {!open && turn.summary}
        </button>
        {turn.uncertain && (
          <Popover>
            <PopoverTrigger asChild>
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label={`Why turn ${turn.turn_index + 1} is uncertain`}
              >
                <CircleHelp className="text-muted-foreground" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" collisionPadding={{ top: 160, bottom: 12 }}>
              <p className="text-xs font-medium text-muted-foreground">The judge was uncertain</p>
              <p className="mt-1 text-sm">{turn.uncertain}</p>
              {trace.is_owner && (
                <PopoverClose asChild>
                  <Button
                    size="xs"
                    variant="outline"
                    className="mt-3"
                    onClick={() => {
                      onExpand();
                      setRelabelSignal((n) => n + 1);
                    }}
                  >
                    <Tags /> Relabel
                  </Button>
                </PopoverClose>
              )}
            </PopoverContent>
          </Popover>
        )}
        {turn.provenance === "human" && (
          <Popover>
            <PopoverTrigger asChild>
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label={`Turn ${turn.turn_index + 1} is labeled by the owner`}
              >
                <UserCheck className="text-muted-foreground" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" collisionPadding={{ top: 160, bottom: 12 }} className="text-sm">
              Labeled by the owner — the judge never re-judges this turn.
            </PopoverContent>
          </Popover>
        )}
      </div>

      {open && (
        <div className="pb-3 pl-5">
          <TurnDetailBody
            trace={trace}
            turn={turn}
            spawns={spawns}
            nav={nav}
            onAnalysisChange={onAnalysisChange}
            relabelSignal={relabelSignal}
          />
        </div>
      )}
    </li>
  );
}

/** A turn's analysis detail — the uncertainty, summary, categories, failure
 *  modes (each opening its reason and evidence), relabel for the owner.
 *  Shared by the expanded turn row and the turn span's panel. */
export function TurnDetailBody({
  trace,
  turn,
  spawns = [],
  nav,
  onAnalysisChange,
  relabelSignal = 0,
}: {
  trace: TraceDetail;
  turn: TurnAnalysis;
  spawns?: AgentSpawn[];
  nav: Nav;
  onAnalysisChange: (analysis: TraceAnalysis) => void;
  relabelSignal?: number;
}) {
  const source = loadedSource(trace, nav);
  const categories = labelsOf(turn, "task_category");
  const failures = labelsOf(turn, "failure_mode");
  const skillUses = turnSkills(trace, turn);
  return (
    <div className="flex flex-col gap-2">
      {turn.uncertain && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <CircleHelp className="mt-px size-3 shrink-0" />
          <span>Uncertain: {turn.uncertain}</span>
        </p>
      )}
      {turn.summary && <p className="text-sm">{turn.summary}</p>}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {categories.map((label) => (
            <LabelPill key={label.value} field="task_category" value={label.value} source={source} />
          ))}
        </div>
      )}
      {failures.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {failures.map((label) => (
            <li key={label.value} className="flex min-w-0 items-baseline gap-1.5">
              <LabelPill field="failure_mode" value={label.value} source={source} />
              {label.reason && (
                <ExpandableText
                  text={label.reason}
                  lines={1}
                  className="min-w-0 flex-1 text-xs text-muted-foreground"
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {skillUses.size > 0 && (
        <div className="flex flex-wrap gap-1">
          {[...skillUses].map(([name, uses]) => (
            <SkillPill key={name} name={name} uses={uses} source={source} />
          ))}
        </div>
      )}
      {spawns.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {spawns.map((a) => (
            <li key={a.span_id} className="flex min-w-0 items-center gap-1.5 text-xs">
              <SubagentIcon
                className="size-3 shrink-0 text-muted-foreground"
                style={{ marginLeft: a.depth * 12 }}
              />
              {a.linked && nav.openAgent ? (
                <button
                  type="button"
                  onClick={() => nav.openAgent?.(a.span_id)}
                  className="min-w-0 truncate rounded-sm text-left hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                  title={a.description ?? undefined}
                >
                  {a.description ?? "Subagent"}
                </button>
              ) : (
                <span className="min-w-0 truncate text-muted-foreground" title={a.description ?? undefined}>
                  {a.description ?? "Subagent"}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {trace.is_owner && (
        <div className="flex justify-end">
          <RelabelTurn
            traceId={trace.trace_id}
            turn={turn}
            onSaved={onAnalysisChange}
            openSignal={relabelSignal}
          />
        </div>
      )}
    </div>
  );
}

/** The skills a turn used, with how often. */
function turnSkills(trace: TraceDetail, turn: TurnAnalysis): Map<string, number> {
  const counts = new Map<string, number>();
  for (const use of trace.skills ?? []) {
    if (use.turn_index === turn.turn_index) counts.set(use.name, (counts.get(use.name) ?? 0) + 1);
  }
  return counts;
}
