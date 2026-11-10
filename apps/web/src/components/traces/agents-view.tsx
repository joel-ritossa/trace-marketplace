"use client";

// The subagent layout: spawns grouped by the turn that started them, each
// group a swimlane timeline on a shared time axis (parallel fan-outs overlap;
// background agents run past the turn's end marker). A lane opens the
// subagent (scopes the evidence pane to its subtree).

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ChevronRight, GitFork } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ExpandableText } from "@/components/ui/expandable-text";
import type { AgentSpawn } from "@/lib/api/traces";
import { formatCompact, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The one icon for subagents, everywhere. */
export const SubagentIcon = GitFork;

/** A turn's ask and time span, from its turn span. */
export type TurnInfo = { ask: string; start: number; end: number };

// Lanes rendered per group before "Show N more".
const LANE_WINDOW = 25;

const time = (iso: string) => new Date(iso).getTime();
const tokens = (a: AgentSpawn) => a.input_tokens + a.output_tokens;

/** Most spawns running at the same instant. */
export function maxConcurrent(agents: AgentSpawn[]): number {
  const edges = agents.flatMap((a) => [
    [time(a.started_at), 1] as const,
    [time(a.ended_at), -1] as const,
  ]);
  edges.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  let live = 0;
  let max = 0;
  for (const [, delta] of edges) max = Math.max(max, (live += delta));
  return max;
}

/** "12 in 4 turns · up to 5 at once" — concurrency over spawns with
 *  transcripts only (the others know just their spawn call). */
export function subagentLine(count: number, turns: number, agents?: AgentSpawn[]): string {
  const base = `${count} in ${turns} turn${turns === 1 ? "" : "s"}`;
  const linked = agents?.filter((a) => a.linked) ?? [];
  return linked.length > 0 ? `${base} · up to ${maxConcurrent(linked)} at once` : base;
}

type Filter = "all" | "errors" | "background";
type Sort = "start" | "duration";

const FILTERS: { key: Filter; label: string; match: (a: AgentSpawn) => boolean }[] = [
  { key: "all", label: "All", match: () => true },
  { key: "errors", label: "With errors", match: (a) => a.status === "error" || a.error_count > 0 },
  { key: "background", label: "Background", match: (a) => a.background === true },
];

/** Spawn order with nested spawns right under their parent. */
function nestedOrder(agents: AgentSpawn[], sort: Sort): AgentSpawn[] {
  const byParent = new Map<string | null, AgentSpawn[]>();
  const ids = new Set(agents.map((a) => a.span_id));
  for (const a of agents) {
    const parent = a.parent_span_id && ids.has(a.parent_span_id) ? a.parent_span_id : null;
    byParent.set(parent, [...(byParent.get(parent) ?? []), a]);
  }
  const key = (a: AgentSpawn) =>
    sort === "duration" ? -(time(a.ended_at) - time(a.started_at)) : time(a.started_at);
  const out: AgentSpawn[] = [];
  const walk = (parent: string | null) => {
    for (const a of [...(byParent.get(parent) ?? [])].sort((x, y) => key(x) - key(y))) {
      out.push(a);
      walk(a.span_id);
    }
  };
  walk(null);
  return out;
}

export function AgentsView({
  agents,
  turns,
  onOpen,
  focus,
}: {
  agents: AgentSpawn[];
  turns: Map<number, TurnInfo>;
  onOpen: (spanId: string) => void;
  // Scroll to a turn's group (turn-row markers); seq re-fires.
  focus?: { turn: number; seq: number } | null;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("start");
  // Spawns without a transcript know only their ~100 ms spawn call: folded
  // into one row per group by default, and left out of every timing figure.
  const [withTranscript, setWithTranscript] = useState(true);
  const shown = agents.filter(FILTERS.find((f) => f.key === filter)!.match);

  const groups = useMemo(() => {
    const map = new Map<number | null, AgentSpawn[]>();
    for (const a of shown) map.set(a.turn_index, [...(map.get(a.turn_index) ?? []), a]);
    return [...map].sort(([x], [y]) => (x ?? -1) - (y ?? -1));
  }, [shown]);

  const linked = agents.filter((a) => a.linked);
  const turnCount = new Set(agents.map((a) => a.turn_index)).size;
  const errors = agents.filter((a) => a.status === "error" || a.error_count > 0).length;
  const total = linked.reduce((sum, a) => sum + tokens(a), 0);
  // Background only filters anything when the set is mixed.
  const backgroundMixed =
    agents.some((a) => a.background === true) && agents.some((a) => a.background !== true);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex flex-wrap gap-x-3 gap-y-1">
          <span>
            <span className="font-mono text-foreground">{agents.length}</span> subagents ·{" "}
            <span className="font-mono text-foreground">{linked.length}</span> with transcripts
          </span>
          <span>
            in <span className="font-mono text-foreground">{turnCount}</span> turns
          </span>
          {linked.length > 0 && (
            <>
              <span title="Most subagents with transcripts running at the same instant">
                up to <span className="font-mono text-foreground">{maxConcurrent(linked)}</span> at
                once
              </span>
              <span title={`${total.toLocaleString()} tokens, subagents with transcripts`}>
                <span className="font-mono text-foreground">{formatCompact(total)}</span> tokens
              </span>
            </>
          )}
          {errors > 0 && (
            <span className="text-error-deep">
              <span className="font-mono">{errors}</span> with errors
            </span>
          )}
        </span>
        <span className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5">
            <Switch
              checked={withTranscript}
              onCheckedChange={setWithTranscript}
              aria-label="Fold subagents without a transcript"
            />
            Only with transcript
          </label>
          {/* Segmented: one filter at a time. */}
          <span role="radiogroup" aria-label="Filter subagents" className="inline-flex rounded-md border p-0.5">
            {FILTERS.filter((f) => f.key !== "background" || backgroundMixed).map(
              ({ key, label, match }) => (
                <button
                  key={key}
                  type="button"
                  role="radio"
                  aria-checked={filter === key}
                  disabled={key !== "all" && !agents.some(match)}
                  onClick={() => setFilter(key)}
                  className={cn(
                    "rounded px-2 py-0.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50",
                    filter === key
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ),
            )}
          </span>
          <Select value={sort} onValueChange={(v) => setSort(v as Sort)}>
            <SelectTrigger size="sm" aria-label="Sort lanes within each turn" className="h-7 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              <SelectItem value="start" className="text-xs">
                By start time
              </SelectItem>
              <SelectItem value="duration" className="text-xs">
                By run time
              </SelectItem>
            </SelectContent>
          </Select>
        </span>
      </div>
      {groups.length === 0 && (
        <p className="text-sm text-muted-foreground">No subagents match this filter.</p>
      )}
      {groups.map(([turn, list]) => (
        <TurnGroup
          key={turn ?? "none"}
          turn={turn}
          info={turn === null ? undefined : turns.get(turn)}
          agents={nestedOrder(list, sort)}
          foldUnlinked={withTranscript}
          onOpen={onOpen}
          focus={focus && focus.turn === turn ? focus.seq : 0}
        />
      ))}
    </div>
  );
}

/** "general-purpose" → "general"; full name on hover. */
const shortType = (type: string) => type.split(/[-:]/)[0] || type;

const TURN_TIP = "Turn duration: the turn span, start → end";
const RUN_TIP = "Run time: spawn → the subagent's last span";

function TurnGroup({
  turn,
  info,
  agents,
  foldUnlinked,
  onOpen,
  focus,
}: {
  turn: number | null;
  info?: TurnInfo;
  agents: AgentSpawn[];
  foldUnlinked: boolean;
  onOpen: (spanId: string) => void;
  focus: number;
}) {
  const linked = agents.filter((a) => a.linked);
  const unlinked = agents.filter((a) => !a.linked);
  const lanes = foldUnlinked ? linked : agents;
  const [open, setOpen] = useState(lanes.length > 0);
  const [showUnlinked, setShowUnlinked] = useState(false);
  const [limit, setLimit] = useState(LANE_WINDOW);
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (focus > 0) {
      setOpen(true);
      ref.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [focus]);

  // The axis runs from the turn's start to the latest end among the lanes
  // drawn (linked only by default); the turn's own end is a faint line.
  const timed = lanes.length > 0 ? lanes : [];
  const t0 = Math.min(info?.start ?? Infinity, ...timed.map((a) => time(a.started_at)));
  const t1 = Math.max(info?.end ?? -Infinity, ...timed.map((a) => time(a.ended_at)));
  const span = Math.max(1, t1 - t0);
  const pct = (t: number) => ((t - t0) / span) * 100;
  const turnEnd = info ? pct(info.end) : null;
  // "bg" only where it distinguishes.
  const bgMixed = lanes.some((a) => a.background === true) && lanes.some((a) => a.background !== true);

  return (
    <section ref={ref} className="scroll-mt-2 rounded-lg border">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ChevronRight
          className={cn("size-3 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")}
        />
        <span className="shrink-0 font-mono text-xs text-muted-foreground">
          {turn === null ? "No turn" : `Turn ${turn + 1}`}
        </span>
        <span className="min-w-0 flex-1 truncate" title={info?.ask}>
          {info?.ask ?? ""}
        </span>
        <span className="shrink-0 font-mono text-xs text-muted-foreground">
          <span title={`${linked.length} with transcript, ${unlinked.length} without`}>
            {agents.length} subagent{agents.length === 1 ? "" : "s"}
          </span>
          {info && <span title={TURN_TIP}> · turn {formatDuration(info.end - info.start)}</span>}
        </span>
      </button>
      {open && (
        <div className="border-t px-3 py-2">
          <ol className="flex flex-col gap-1">
            {lanes.length > 0 && (
              // Labels for the lanes' right-hand figures.
              <li
                aria-hidden
                className={cn(LANE_GRID, "text-[11px] text-muted-foreground")}
              >
                <span />
                <span />
                <span />
                <span className="pl-2 text-right">run time · steps · tokens</span>
              </li>
            )}
            {info && lanes.length > 0 && (
              <li className="py-0.5">
                <Lane
                  label="Main agent (this turn)"
                  muted
                  start={pct(info.start)}
                  end={pct(info.end)}
                  marker={turnEnd}
                  stats={<span title={TURN_TIP}>{formatDuration(info.end - info.start)}</span>}
                />
              </li>
            )}
            {lanes.slice(0, limit).map((a) => (
              <AgentLane
                key={a.span_id}
                agent={a}
                pct={pct}
                marker={turnEnd}
                showBg={bgMixed}
                onOpen={onOpen}
              />
            ))}
          </ol>
          {lanes.length > limit && (
            <Button
              size="xs"
              variant="ghost"
              className="mt-1 text-muted-foreground"
              onClick={() => setLimit((n) => n + LANE_WINDOW)}
            >
              Show {Math.min(LANE_WINDOW, lanes.length - limit)} more of {lanes.length - limit}
            </Button>
          )}
          {foldUnlinked && unlinked.length > 0 && (
            <div className={cn(lanes.length > 0 && "mt-1 border-t pt-1")}>
              <button
                type="button"
                aria-expanded={showUnlinked}
                onClick={() => setShowUnlinked((v) => !v)}
                className="flex w-full items-center gap-1.5 rounded-sm py-1 text-left text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                title="Launched as background agents whose transcripts were not uploaded: only the spawn call is known"
              >
                <ChevronRight
                  className={cn("size-3 shrink-0 transition-transform", showUnlinked && "rotate-90")}
                />
                {unlinked.length} launched without transcript · {showUnlinked ? "hide" : "show"}
              </button>
              {showUnlinked && (
                <ul className="flex flex-col gap-0.5 pb-1 pl-4.5">
                  {unlinked.map((a) => (
                    <li
                      key={a.span_id}
                      className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground"
                      style={{ paddingLeft: a.depth * 12 }}
                    >
                      <span className="min-w-0 truncate" title={a.description ?? undefined}>
                        {a.description ?? "Subagent"}
                      </span>
                      {a.type && <span className="shrink-0 text-foreground/60">{a.type}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// One grid for every lane and the main-agent row, so bars share an axis:
// description | type | bar track | stats.
const LANE_GRID = "grid grid-cols-[minmax(0,1fr)_4.5rem_minmax(6rem,26%)_10rem] items-center";

/** The lane grid: label | bar | stats, the bar column shared by the group
 *  (the turn-end marker uses the same variables). */
function Lane({
  label,
  start,
  end,
  stats,
  muted = false,
  error = false,
  dashed = false,
  indent = 0,
  badges,
  marker = null,
}: {
  marker?: number | null;
  label: ReactNode;
  start: number;
  end: number;
  stats: ReactNode;
  muted?: boolean;
  error?: boolean;
  dashed?: boolean;
  indent?: number;
  badges?: ReactNode;
}) {
  return (
    <span className={cn(LANE_GRID, "text-xs")}>
      <span className="min-w-0 pr-2" style={{ paddingLeft: indent * 12 }}>
        <span className={cn("block min-w-0", muted && "text-muted-foreground")}>{label}</span>
      </span>
      <span className="flex min-w-0 items-center gap-1 pr-2">{badges}</span>
      <span className="relative h-4 rounded-sm bg-agentprism-secondary">
        {/* The turn's end, faint (background agents may run past it). */}
        {marker !== null && marker < 99.5 && (
          <span
            aria-hidden
            className="absolute inset-y-0 w-px bg-muted-foreground/40"
            style={{ left: `${marker}%` }}
          />
        )}
        <span
          className={cn(
            "absolute top-1/2 h-1.5 -translate-y-1/2 rounded-sm",
            error ? "bg-error" : muted ? "bg-muted-foreground/40" : "bg-agentprism-timeline-agent",
            dashed && "border border-dashed border-muted-foreground bg-transparent",
          )}
          style={{ left: `${start}%`, width: `max(4px, ${Math.max(0, end - start)}%)` }}
        />
      </span>
      <span className="truncate pl-2 text-right font-mono text-muted-foreground">{stats}</span>
    </span>
  );
}

function AgentLane({
  agent: a,
  pct,
  marker,
  showBg,
  onOpen,
}: {
  agent: AgentSpawn;
  pct: (t: number) => number;
  marker: number | null;
  showBg: boolean;
  onOpen: (spanId: string) => void;
}) {
  const error = a.status === "error" || a.error_count > 0;
  const body = (
    <Lane
      marker={marker}
      indent={a.depth}
      error={error}
      dashed={!a.linked}
      muted={!a.linked}
      start={pct(time(a.started_at))}
      end={pct(time(a.ended_at))}
      label={
        <span className="block truncate text-sm" title={a.description ?? undefined}>
          {a.description ?? "Subagent"}
        </span>
      }
      badges={
        <>
          {(a.type || a.model) && (
            <span
              className="min-w-0 truncate rounded-full bg-secondary px-1.5 text-foreground/75"
              title={[a.type, a.model].filter(Boolean).join(" · ")}
            >
              {shortType(a.type ?? a.model ?? "")}
            </span>
          )}
          {showBg && a.background && (
            <span
              className="shrink-0 rounded-full bg-secondary px-1.5 text-foreground/75"
              title="Background agent: may outlive its turn"
            >
              bg
            </span>
          )}
        </>
      }
      stats={
        !a.linked ? (
          <span title="Transcript not uploaded: only the spawn call is known">no transcript</span>
        ) : (
        <span>
          <span title={RUN_TIP}>{formatDuration(time(a.ended_at) - time(a.started_at))}</span> ·{" "}
          <span title="Steps: spans in its own stream">{a.own_span_count}</span> ·{" "}
          <span title={`${tokens(a).toLocaleString()} tokens`}>{formatCompact(tokens(a))}</span>
          {error && <span className="ml-1 text-error-deep">●{a.error_count || ""}</span>}
        </span>
        )
      }
    />
  );
  return (
    <li>
      {a.linked ? (
        <button
          type="button"
          onClick={() => onOpen(a.span_id)}
          className="block w-full rounded-sm py-0.5 text-left transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          title={`Open subagent: ${a.description ?? ""}`}
        >
          {body}
        </button>
      ) : (
        <div className="py-0.5 opacity-70">{body}</div>
      )}
    </li>
  );
}

/** The spawn's identity and totals, shared by the scope header and the
 *  span panel of an `Agent: …` span. */
export function SubagentCard({
  agent: a,
  turnLabel,
  parentLabel,
  brief,
  report,
  action,
  compact = false,
}: {
  agent: AgentSpawn;
  turnLabel: string;
  parentLabel: string;
  brief: string | null | undefined;
  report: string | null | undefined;
  action?: ReactNode;
  // One stats line and one-line brief/report (expandable): the scope header,
  // where the conversation below needs the room.
  compact?: boolean;
}) {
  const facts: [string, string][] = [
    ["Duration", formatDuration(time(a.ended_at) - time(a.started_at))],
    ["Steps", String(a.own_span_count)],
    ["Tokens", formatCompact(tokens(a))],
    ["Errors", String(a.error_count)],
  ];
  const prose = (title: string, text: string | null | undefined) => (
    <div className={cn(compact && "flex min-w-0 items-baseline gap-2")}>
      <h4 className="shrink-0 text-xs text-muted-foreground">{title}</h4>
      {text ? (
        <ExpandableText
          text={text}
          lines={compact ? 1 : 3}
          className={cn("text-sm", compact ? "min-w-0 flex-1" : "mt-0.5")}
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          {text === undefined ? "Loading…" : "Not recorded."}
        </p>
      )}
    </div>
  );
  if (compact)
    return (
      <div className="flex flex-col gap-1.5">
        <p className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <SubagentIcon className="size-3.5 shrink-0" />
          <span className="text-sm font-semibold text-foreground">{a.description ?? "Subagent"}</span>
          {a.type && <span>{a.type}</span>}
          {a.model && <span className="font-mono">{a.model}</span>}
          {facts.map(([k, v]) => (
            <span key={k} className={cn(k === "Errors" && a.error_count > 0 && "text-error-deep")}>
              <span className="font-mono text-foreground">{v}</span> {k.toLowerCase()}
            </span>
          ))}
          <span>
            spawned in {turnLabel} by {parentLabel}
          </span>
        </p>
        {prose("Brief", brief)}
        {prose("Final report", report)}
      </div>
    );
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <SubagentIcon className="size-4 shrink-0 text-muted-foreground" />
        <h3 className="min-w-0 flex-1 text-sm font-semibold">{a.description ?? "Subagent"}</h3>
        {action}
      </div>
      <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {a.type && <span>{a.type}</span>}
        {a.model && <span className="font-mono">{a.model}</span>}
        {a.background && <span>background</span>}
        <span>
          spawned in {turnLabel} by {parentLabel}
        </span>
      </p>
      <dl className="grid grid-cols-4 gap-2">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className={cn("font-mono text-xs", k === "Errors" && a.error_count > 0 && "text-error-deep")}>
              {v}
            </dd>
          </div>
        ))}
      </dl>
      {prose("Brief", brief)}
      {prose("Final report", report)}
    </div>
  );
}
