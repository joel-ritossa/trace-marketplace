"use client";

// The one popover family for analysis pills, everywhere they render: a label
// pill (category / failure mode) lists the turns that carry it; a group
// control ("+N", the failure-mode count) lists labels that expand in place to
// the same body; the outcome badge shows the goal and summary. On the trace
// page the turns are in hand; list rows fetch the trace detail lazily when a
// popover first opens and navigate to the trace page for "Go to turn" /
// "Open evidence".

import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronRight, Loader2, Puzzle, TriangleAlert } from "lucide-react";
import { describe, humanize } from "@/components/review/taxonomy";
import {
  AnalysisStatusBadge,
  BADGE,
  LabelChip,
  NEUTRAL,
  OutcomeBadge,
} from "@/components/traces/badges";
import { Button } from "@/components/ui/button";
import { ExpandableText } from "@/components/ui/expandable-text";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  getTrace,
  type AnalysisStatus,
  type Outcome,
  type SessionAnalysis,
  type SkillUse,
  type TraceDetail,
  type TurnAnalysis,
  type TurnLabel,
} from "@/lib/api/traces";
import { cn } from "@/lib/utils";

type Field = TurnLabel["field"];

/** Where a pill's turns come from: the trace page's analysis (with its own
 *  navigation), or a list row's trace id (fetched on first open). */
export type TurnSource =
  | {
      kind: "loaded";
      turns: TurnAnalysis[];
      session: SessionAnalysis;
      skills: SkillUse[];
      goToTurn: (turnIndex: number) => void;
      showSpan: (sourceSpanId: string) => void;
    }
  | { kind: "lazy"; traceId: string };

type Resolved =
  | { phase: "loading" | "error" }
  | {
      phase: "ready";
      turns: TurnAnalysis[];
      session: SessionAnalysis;
      skills: SkillUse[];
      goToTurn: (turnIndex: number) => void;
      showSpan: (sourceSpanId: string) => void;
    };

// One fetch per trace for the page's lifetime; a failure is evicted so the
// next open retries.
const detailCache = new Map<string, Promise<TraceDetail>>();

function cachedTrace(traceId: string): Promise<TraceDetail> {
  let pending = detailCache.get(traceId);
  if (!pending) {
    pending = getTrace(traceId);
    pending.catch(() => detailCache.delete(traceId));
    detailCache.set(traceId, pending);
  }
  return pending;
}

function useResolved(source: TurnSource, open: boolean): Resolved {
  const router = useRouter();
  const traceId = source.kind === "lazy" ? source.traceId : null;
  const [detail, setDetail] = useState<TraceDetail | null | "error">(null);

  useEffect(() => {
    if (!open || traceId === null || (detail !== null && detail !== "error")) return;
    let cancelled = false;
    cachedTrace(traceId)
      .then((trace) => !cancelled && setDetail(trace))
      .catch(() => !cancelled && setDetail("error"));
    return () => {
      cancelled = true;
    };
  }, [open, traceId, detail]);

  if (source.kind === "loaded") return { phase: "ready", ...source };
  if (detail === "error") return { phase: "error" };
  if (detail === null) return { phase: "loading" };
  return {
    phase: "ready",
    turns: detail.analysis.turns,
    session: detail.analysis.session,
    skills: detail.skills ?? [],
    goToTurn: (i) => router.push(`/traces/${source.traceId}?turn=${i}`),
    showSpan: (id) => router.push(`/traces/${source.traceId}?span=${encodeURIComponent(id)}`),
  };
}

const findLabel = (turn: TurnAnalysis, field: Field, value: string) =>
  turn.labels.find((l) => l.field === field && l.value === value);

function carrying(turns: TurnAnalysis[], field: Field, value: string): TurnAnalysis[] {
  return turns.filter((t) => findLabel(t, field, value));
}

const turnsText = (n: number) => `in ${n} turn${n === 1 ? "" : "s"}`;

// Top bar (56px) + the trace page's sticky header strip.
const HEADER_CLEARANCE = 160;

// Pills sit inside table rows and turn-row toggles: their clicks are theirs.
const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

function PanelState({ resolved }: { resolved: Resolved }) {
  if (resolved.phase === "loading")
    return (
      <p className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> Loading turns…
      </p>
    );
  return <p className="py-2 text-xs text-error-deep">Could not load this trace’s turns.</p>;
}

/** "Open evidence", or "Evidence 1, 2…" for several cited spans. */
function EvidenceActions({ spanIds, showSpan }: { spanIds: string[]; showSpan: (id: string) => void }) {
  return spanIds.map((id, i) => (
    <PopoverClose key={id} asChild>
      <Button size="xs" variant="outline" title={id} onClick={() => showSpan(id)}>
        {spanIds.length === 1 ? "Open evidence" : `Evidence ${i + 1}`}
      </Button>
    </PopoverClose>
  ));
}

/** The one popover row for a turn: number, one-line summary, an optional
 *  note (the label's reason, who invoked a skill), "Go to turn" and evidence. */
function TurnRefItem({
  turnIndex,
  summary,
  note,
  spanIds,
  resolved,
}: {
  turnIndex: number | null;
  summary: string | null | undefined;
  note?: ReactNode;
  spanIds: string[];
  resolved: Extract<Resolved, { phase: "ready" }>;
}) {
  return (
    <li className="flex flex-col gap-1 px-4 py-2">
      <p className="flex items-baseline gap-2">
        <span className="shrink-0 font-mono text-xs text-muted-foreground">
          {turnIndex === null ? "No turn" : `Turn ${turnIndex + 1}`}
        </span>
        <ExpandableText
          text={summary ?? "Not judged yet"}
          lines={1}
          className="min-w-0 flex-1 text-sm"
        />
      </p>
      {note}
      <div className="flex flex-wrap gap-1">
        {turnIndex !== null && (
          <PopoverClose asChild>
            <Button size="xs" variant="outline" onClick={() => resolved.goToTurn(turnIndex)}>
              Go to turn
            </Button>
          </PopoverClose>
        )}
        <EvidenceActions spanIds={spanIds} showSpan={resolved.showSpan} />
      </div>
    </li>
  );
}

// Rows a popover list shows before "Show all N turns".
const LIST_WINDOW = 6;

/** A popover's bounded list: whole items only, the rest behind "Show all";
 *  the list scrolls inside the popover's available height. */
function RefList({ count, children }: { count: number; children: (limit: number) => ReactNode }) {
  const [all, setAll] = useState(false);
  const limit = all ? count : LIST_WINDOW;
  return (
    <div className="-mx-4 flex min-h-0 flex-col border-t">
      <ul className="min-h-0 flex-1 divide-y overflow-y-auto">{children(limit)}</ul>
      {count > LIST_WINDOW && !all && (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="shrink-0 border-t px-4 py-1.5 text-left text-xs font-medium text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          Show all {count} turns
        </button>
      )}
    </div>
  );
}

/** The turns that carry one label: number, one-line summary, the label's
 *  reason (failure modes), actions. */
function TurnList({
  field,
  value,
  resolved,
}: {
  field: Field;
  value: string;
  resolved: Extract<Resolved, { phase: "ready" }>;
}) {
  const turns = carrying(resolved.turns, field, value);
  if (turns.length === 0)
    return <p className="py-2 text-xs text-muted-foreground">No judged turn carries it.</p>;
  return (
    <RefList count={turns.length}>
      {(limit) =>
        turns.slice(0, limit).map((turn) => {
          const label = findLabel(turn, field, value)!;
          return (
            <TurnRefItem
              key={turn.turn_index}
              turnIndex={turn.turn_index}
              summary={turn.summary}
              resolved={resolved}
              spanIds={field === "failure_mode" ? label.span_ids : []}
              note={
                field === "failure_mode" &&
                label.reason && (
                  <ExpandableText
                    text={label.reason}
                    lines={2}
                    className="text-xs text-muted-foreground"
                  />
                )
              }
            />
          );
        })
      }
    </RefList>
  );
}

/** A failure-mode pill with its own cited reason and evidence (a subagent
 *  verdict has no turns to list). */
export function EvidencePill({
  value,
  reason,
  spanIds,
  showSpan,
}: {
  value: string;
  reason: string;
  spanIds: string[];
  showSpan: (id: string) => void;
}) {
  const description = describe(value);
  return (
    <Popover>
      <PopoverTrigger asChild onClick={stop}>
        <LabelChip
          field="failure_mode"
          value={value}
          title={description}
          data-pill="failure_mode"
          className="min-w-0 max-w-32"
        />
      </PopoverTrigger>
      <PopoverContent
        align="start"
        collisionPadding={{ top: HEADER_CLEARANCE, bottom: 12, left: 12, right: 12 }}
        className="flex w-80 flex-col gap-1"
        onClick={stop}
      >
        <p className="text-sm font-medium">{humanize(value)}</p>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
        <ExpandableText text={reason} lines={3} className="text-sm" />
        <div className="flex flex-wrap gap-1 pt-1">
          <EvidenceActions spanIds={spanIds} showSpan={showSpan} />
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** A label's popover body: title + turn count, its description, its turns. */
function LabelBody({ field, value, resolved }: { field: Field; value: string; resolved: Resolved }) {
  const description = describe(value);
  return (
    <>
      <p className="flex items-baseline justify-between gap-3 text-sm font-medium">
        <span className="min-w-0 truncate">{humanize(value)}</span>
        {resolved.phase === "ready" && (
          <span className="shrink-0 font-mono text-xs font-normal text-muted-foreground">
            {turnsText(carrying(resolved.turns, field, value).length)}
          </span>
        )}
      </p>
      {description && <p className="mt-0.5 mb-2 text-xs text-muted-foreground">{description}</p>}
      {resolved.phase === "ready" ? (
        <TurnList field={field} value={value} resolved={resolved} />
      ) : (
        <PanelState resolved={resolved} />
      )}
    </>
  );
}

/** A popover whose content resolves its source only once opened. */
function SourcePopover({
  source,
  trigger,
  children,
  className,
}: {
  source: TurnSource;
  trigger: ReactNode;
  children: (resolved: Resolved) => ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const resolved = useResolved(source, open);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild onClick={stop}>
        {trigger}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        // Below or beside, never over the sticky page header; the content
        // fits the room left and scrolls inside.
        collisionPadding={{ top: HEADER_CLEARANCE, bottom: 12, left: 12, right: 12 }}
        className={cn(
          "flex max-h-[min(32rem,var(--radix-popover-content-available-height))] w-80 flex-col",
          className,
        )}
        onClick={stop}
      >
        {children(resolved)}
      </PopoverContent>
    </Popover>
  );
}

/** One label pill that opens its turns. */
export function LabelPill({
  field,
  value,
  source,
  className,
}: {
  field: Field;
  value: string;
  source: TurnSource;
  className?: string;
}) {
  return (
    <SourcePopover
      source={source}
      trigger={
        <LabelChip
          field={field}
          value={value}
          className={className}
          title={describe(value)}
          data-pill={field}
        />
      }
    >
      {(resolved) => <LabelBody field={field} value={value} resolved={resolved} />}
    </SourcePopover>
  );
}

/** A custom trigger (e.g. the session card's failure-mode row) for the same
 *  label popover. */
export function LabelPopover({
  field,
  value,
  source,
  children,
  footer,
}: {
  field: Field;
  value: string;
  source: TurnSource;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <SourcePopover source={source} trigger={children}>
      {(resolved) => (
        <>
          <LabelBody field={field} value={value} resolved={resolved} />
          {footer}
        </>
      )}
    </SourcePopover>
  );
}

/** Several labels behind one control ("+N", the failure-mode count): each
 *  row expands in place to the label's body. */
export function LabelGroupPopover({
  field,
  values,
  source,
  title,
  trigger,
}: {
  field: Field;
  values: string[];
  source: TurnSource;
  title: string;
  trigger: ReactNode;
}) {
  return (
    <SourcePopover source={source} trigger={trigger}>
      {(resolved) => <GroupBody field={field} values={values} resolved={resolved} title={title} />}
    </SourcePopover>
  );
}

function GroupBody({
  field,
  values,
  resolved,
  title,
}: {
  field: Field;
  values: string[];
  resolved: Resolved;
  title: string;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <>
      <p className="mb-2 flex items-baseline justify-between gap-3 text-sm font-medium">
        {title}
        <span className="text-xs font-normal text-muted-foreground">
          {values.length} {field === "failure_mode" ? "modes" : "categories"}
        </span>
      </p>
      <ul className="-mx-4 min-h-0 flex-1 overflow-y-auto border-t">
        {values.map((value) => {
          const open = expanded === value;
          return (
            <li key={value} className="border-b last:border-b-0">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setExpanded(open ? null : value)}
                className="flex w-full items-center gap-2 px-4 py-1.5 text-left text-sm transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none"
                title={describe(value)}
              >
                <ChevronRight
                  className={cn(
                    "size-3 shrink-0 text-muted-foreground transition-transform",
                    open && "rotate-90",
                  )}
                />
                {field === "failure_mode" && (
                  <TriangleAlert className="size-3 shrink-0 text-error-deep" />
                )}
                <span className="min-w-0 flex-1 truncate">{humanize(value)}</span>
                {resolved.phase === "ready" && (
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {turnsText(carrying(resolved.turns, field, value).length)}
                  </span>
                )}
              </button>
              {open && (
                <div className="px-4 pb-2">
                  {describe(value) && (
                    <p className="mb-1 text-xs text-muted-foreground">{describe(value)}</p>
                  )}
                  {resolved.phase === "ready" ? (
                    <TurnList field={field} value={value} resolved={resolved} />
                  ) : (
                    <PanelState resolved={resolved} />
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/** The failure-mode count ("⚠ 5") as a control that lists them. */
export function FailureCountPopover({ values, source }: { values: string[]; source: TurnSource }) {
  if (values.length === 0) return null;
  return (
    <LabelGroupPopover
      field="failure_mode"
      values={values}
      source={source}
      title="Failure modes"
      trigger={
        <button
          type="button"
          data-pill="failures"
          className={cn(
            BADGE,
            NEUTRAL,
            "font-normal transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
          )}
          title={`Failure modes: ${values.map(humanize).join(", ")}`}
        >
          <TriangleAlert className="size-3 text-error-deep" />
          {values.length}
        </button>
      }
    />
  );
}

/** The outcome badge as a control: the session's goal and summary, or — for
 *  a turn — that turn's summary. */
export function OutcomePill({
  outcome,
  source,
  turn,
}: {
  outcome: Outcome;
  source: TurnSource;
  turn?: TurnAnalysis;
}) {
  return (
    <SourcePopover
      source={source}
      trigger={
        <button
          type="button"
          data-pill="outcome"
          className="shrink-0 rounded-full focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          title={turn ? "Turn verdict — show its summary" : "Session verdict — show goal and summary"}
        >
          <OutcomeBadge outcome={outcome} />
        </button>
      }
    >
      {(resolved) => (
        <>
          <p className="flex items-center gap-2 text-sm font-medium">
            {turn ? `Turn ${turn.turn_index + 1}` : "Session"} <OutcomeBadge outcome={outcome} />
          </p>
          {turn ? (
            <p className="mt-2 text-sm">{turn.summary ?? "No summary recorded."}</p>
          ) : resolved.phase === "ready" ? (
            <div className="mt-2 flex max-h-72 flex-col gap-2 overflow-y-auto">
              {resolved.session.goal && (
                <div>
                  <p className="text-xs text-muted-foreground">Goal</p>
                  <p className="text-sm">{resolved.session.goal}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-muted-foreground">What happened</p>
                <p className="text-sm">{resolved.session.summary ?? "No summary recorded."}</p>
              </div>
            </div>
          ) : (
            <PanelState resolved={resolved} />
          )}
        </>
      )}
    </SourcePopover>
  );
}

/** Category chips a list row may show before "+N" (the session arrays arrive
 *  most-frequent first, so these are the dominant ones). Fewer show when the
 *  column is narrow: a chip is either whole or folded into "+N". */
export const LIST_LABEL_CAP = 2;

/** A session's labels in one row-height line for list rows: the top
 *  categories as pills, "+N" opening all of them, then the failure-mode count.
 *  Every control opens the shared popovers, fetching the trace on first open. */
export function LabelSummary({
  traceId,
  taskCategories,
  failureModes,
  skillNames = [],
  skillFilter,
}: {
  traceId: string;
  taskCategories: string[];
  failureModes: string[];
  skillNames?: string[];
  skillFilter?: SkillFilter;
}) {
  const source = useLazySource(traceId);
  const capped = taskCategories.slice(0, LIST_LABEL_CAP);
  const ref = useRef<HTMLSpanElement>(null);
  const skillsRef = useRef<HTMLSpanElement>(null);
  const [fit, setFit] = useState(capped.length);

  // Whole chips only: the chips sit in a one-line box that wraps and hides
  // overflow. A measure pass shows them all, counts those left on the first
  // line and takes the rest out of layout (no gap); "+N" folds them in. It
  // runs after each render and whenever the box or its cell resizes (incl.
  // web fonts landing) — the DOM-only toggle keeps it from re-rendering.
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const measure = () => {
      const chips = [...box.children] as HTMLElement[];
      for (const chip of chips) chip.style.display = "";
      // On the first line and not cut by the box's right edge (a lone first
      // chip can't wrap, so it would otherwise be clipped mid-chip).
      const top = chips[0]?.offsetTop ?? 0;
      const right = box.getBoundingClientRect().right + 0.5;
      const count = chips.filter(
        (c) => c.offsetTop === top && c.getBoundingClientRect().right <= right,
      ).length;
      chips.forEach((chip, i) => (chip.style.display = i < count ? "" : "none"));
      setFit(count);
      // The skills pill (lowest priority) shows whole or not at all.
      const skills = skillsRef.current?.lastElementChild as HTMLElement | null;
      const edge = box.parentElement?.getBoundingClientRect().right;
      if (skills && edge !== undefined) {
        skills.style.visibility = "";
        if (skills.getBoundingClientRect().right > edge + 0.5) skills.style.visibility = "hidden";
      }
    };
    measure();
    const observer = new ResizeObserver(() => measure());
    observer.observe(box.closest("td") ?? box.parentElement ?? box);
    let live = true;
    document.fonts?.ready.then(() => live && measure());
    return () => {
      live = false;
      observer.disconnect();
    };
  });

  const hidden = taskCategories.length - Math.min(fit, capped.length);
  const matchedSkill = skillNames.find((n) => skillFilter?.active.includes(n));
  return (
    <>
      {capped.length > 0 && (
        <span ref={ref} className="flex h-5 min-w-0 flex-wrap gap-1 overflow-hidden">
          {capped.map((value) => (
            <LabelPill
              key={value}
              field="task_category"
              value={value}
              source={source}
              className="min-w-0 max-w-32"
            />
          ))}
        </span>
      )}
      {hidden > 0 && (
        <LabelGroupPopover
          field="task_category"
          values={taskCategories}
          source={source}
          title="Task categories"
          trigger={
            <button
              type="button"
              data-pill="more"
              className="shrink-0 rounded-sm px-0.5 font-mono text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
              title={`Show all ${taskCategories.length} categories`}
            >
              +{hidden}
            </button>
          }
        />
      )}
      <FailureCountPopover values={failureModes} source={source} />
      {skillNames.length > 0 && (
        // Lowest priority (shrinks first; a pill that no longer fits wraps out
        // of the one-line box whole) — unless it names why the row matched the
        // active skill filter.
        <span
          ref={skillsRef}
          className={cn(
            "flex h-5 min-w-0 overflow-hidden",
            // Below xl the column has no room for it: folded away unless it
            // names the active filter's match.
            matchedSkill ? "max-w-40 shrink-0" : "hidden shrink-[100] flex-wrap xl:flex",
          )}
        >
          {/* A zero-width first item lets the pill wrap out of the line
              (hidden) instead of being clipped; a matched skill truncates. */}
          {!matchedSkill && <span aria-hidden className="h-5 w-0" />}
          <SkillsCountPopover
            names={skillNames}
            source={source}
            matched={matchedSkill}
            onFilter={skillFilter?.add}
          />
        </span>
      )}
    </>
  );
}

/** The current list's skill filter: which skills are active, and how a
 *  popover adds one. */
export type SkillFilter = { active: string[]; add: (name: string) => void };

/** The outcome slot of a row or header: the verdict as a control, else the
 *  honest status pill (with its explanation on hover). */
export function TraceOutcomeControl({
  outcome,
  status,
  failed,
  source,
}: {
  outcome: Outcome | null;
  status: AnalysisStatus;
  failed: boolean;
  source: TurnSource;
}) {
  // The same status on every surface (owner or not).
  if (outcome) return <OutcomePill outcome={outcome} source={source} />;
  return <AnalysisStatusBadge status={status} failed={failed} />;
}

/** The lazy source for a list row, stable per trace id. */
export function useLazySource(traceId: string): TurnSource {
  return useMemo(() => ({ kind: "lazy", traceId }), [traceId]);
}

// Skills: facts about the session (the agent's Skill calls, the user's slash
// commands), not judge labels — same interaction family, own pill. One icon
// everywhere for skills.
export const SkillIcon = Puzzle;

/** "anthropic-skills:pdf" → muted "anthropic-skills:" + "pdf"; full name on hover. */
export function SkillName({ name }: { name: string }) {
  const cut = name.lastIndexOf(":");
  return (
    <span className="min-w-0 truncate" title={name}>
      {cut > 0 && <span className="text-muted-foreground">{name.slice(0, cut + 1)}</span>}
      {name.slice(cut + 1)}
    </span>
  );
}

const usesOf = (skills: SkillUse[], name: string) => skills.filter((u) => u.name === name);

/** One skill's uses: turn, the turn's summary, who invoked it, actions. */
function SkillBody({
  name,
  resolved,
  footer,
}: {
  name: string;
  resolved: Resolved;
  footer?: (name: string) => ReactNode;
}) {
  if (resolved.phase !== "ready") return <PanelState resolved={resolved} />;
  const uses = usesOf(resolved.skills, name);
  return (
    <>
      {uses.length === 0 ? (
        <p className="py-2 text-xs text-muted-foreground">No recorded uses.</p>
      ) : (
        <RefList count={uses.length}>
          {(limit) =>
            uses.slice(0, limit).map((use, i) => (
              <TurnRefItem
                key={`${use.span_id}-${i}`}
                turnIndex={use.turn_index}
                summary={resolved.turns.find((t) => t.turn_index === use.turn_index)?.summary}
                resolved={resolved}
                spanIds={[use.span_id]}
                note={
                  use.source && (
                    <p className="text-xs text-muted-foreground">
                      {use.source === "user" ? "by you (slash command)" : "by the agent"}
                    </p>
                  )
                }
              />
            ))
          }
        </RefList>
      )}
      {footer?.(name)}
    </>
  );
}

const SKILL_PILL = cn(
  BADGE,
  NEUTRAL,
  "font-normal transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
);

/** A skill as a pill ("name ×uses") that opens its uses. */
export function SkillPill({
  name,
  uses,
  source,
  footer,
}: {
  name: string;
  uses: number;
  source: TurnSource;
  footer?: (name: string) => ReactNode;
}) {
  return (
    <SourcePopover
      source={source}
      trigger={
        <button type="button" className={cn(SKILL_PILL, "max-w-48")}>
          <SkillIcon className="size-3 shrink-0" />
          <SkillName name={name} />
          {uses > 1 && <span className="shrink-0 font-mono text-muted-foreground">×{uses}</span>}
        </button>
      }
    >
      {(resolved) => (
        <>
          <p className="mb-2 flex items-baseline justify-between gap-3 text-sm font-medium">
            <SkillName name={name} />
            <span className="shrink-0 font-mono text-xs font-normal text-muted-foreground">
              used {uses}×
            </span>
          </p>
          <SkillBody name={name} resolved={resolved} footer={footer} />
        </>
      )}
    </SourcePopover>
  );
}

/** A list row's skills behind one pill: the count (or the skill the active
 *  filter matched), opening the skills with their uses. */
export function SkillsCountPopover({
  names,
  source,
  matched,
  onFilter,
}: {
  names: string[];
  source: TurnSource;
  matched?: string;
  onFilter?: (name: string) => void;
}) {
  if (names.length === 0) return null;
  return (
    <SourcePopover
      source={source}
      trigger={
        <button
          type="button"
          data-pill="skills"
          className={cn(SKILL_PILL, "min-w-0 max-w-full")}
          title={`Skills: ${names.join(", ")}`}
        >
          <SkillIcon className="size-3 shrink-0" />
          {matched ? <SkillName name={matched} /> : names.length}
        </button>
      }
    >
      {(resolved) => (
        <SkillsGroupBody
          names={names}
          resolved={resolved}
          footer={
            onFilter &&
            ((name) => (
              <PopoverClose asChild>
                <Button size="xs" variant="ghost" className="mt-2" onClick={() => onFilter(name)}>
                  Filter by this skill
                </Button>
              </PopoverClose>
            ))
          }
        />
      )}
    </SourcePopover>
  );
}

function SkillsGroupBody({
  names,
  resolved,
  footer,
}: {
  names: string[];
  resolved: Resolved;
  footer?: (name: string) => ReactNode;
}) {
  const [expanded, setExpanded] = useState<string | null>(names.length === 1 ? names[0] : null);
  return (
    <>
      <p className="mb-2 flex items-baseline justify-between gap-3 text-sm font-medium">
        Skills
        <span className="text-xs font-normal text-muted-foreground">
          {names.length} skill{names.length === 1 ? "" : "s"}
        </span>
      </p>
      <ul className="-mx-4 min-h-0 flex-1 overflow-y-auto border-t">
        {names.map((name) => {
          const open = expanded === name;
          return (
            <li key={name} className="border-b last:border-b-0">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setExpanded(open ? null : name)}
                className="flex w-full items-center gap-2 px-4 py-1.5 text-left text-sm transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none"
              >
                <ChevronRight
                  className={cn(
                    "size-3 shrink-0 text-muted-foreground transition-transform",
                    open && "rotate-90",
                  )}
                />
                <SkillIcon className="size-3 shrink-0 text-muted-foreground" />
                <span className="flex min-w-0 flex-1">
                  <SkillName name={name} />
                </span>
                {resolved.phase === "ready" && (
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">
                    used {usesOf(resolved.skills, name).length}×
                  </span>
                )}
              </button>
              {open && (
                <div className="px-4 pb-2">
                  <SkillBody name={name} resolved={resolved} footer={footer} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
