"use client";

import type { ReactNode } from "react";
import {
  AutomatedMarker,
  ClampedText,
  TurnDetailBody,
  type Nav,
} from "@/components/traces/analysis-section";
import { SubagentCard, SubagentIcon } from "@/components/traces/agents-view";
import { OutcomeBadge } from "@/components/traces/badges";
import { MessageText } from "@/components/traces/conversation-view";
import { ExpandableText } from "@/components/ui/expandable-text";
import { formatCompact, formatDuration } from "@/lib/format";
import { spawnBrief } from "@/components/traces/span-tree";
import { Button } from "@/components/ui/button";
import { stripWrappers } from "@/components/traces/names";
import type { SpanPanelContext } from "@/components/traces/trace-evidence";
import type { AgentSpawn, TraceAnalysis, TraceDetail } from "@/lib/api/traces";

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h4 className="text-xs text-muted-foreground">{title}</h4>
      {children}
    </div>
  );
}

const TURN_NAME = /^turn (\d+)\b/i;

/** The turn index a span stands for: its `turn.index` attribute, or the
 *  importer's "turn N: …" name while the attributes load. */
function turnIndexOf({ node, attributes }: SpanPanelContext): number | null {
  const attr = attributes?.["turn.index"];
  if (typeof attr === "number") return attr;
  if (attributes === null && node.type === "agent_invocation") {
    const match = TURN_NAME.exec(node.title);
    if (match) return Number(match[1]) - 1;
  }
  return null;
}

/** The trace page's panel for session-structure spans: a turn span shows the
 *  user's ask, the agent's final reply and the turn's analysis; the session
 *  root shows the session card. Null for every other span (generic panel). */
export function traceSpanPanel(
  ctx: SpanPanelContext,
  trace: TraceDetail,
  nav: Nav,
  onAnalysisChange: (analysis: TraceAnalysis) => void,
  agents: AgentSpawn[] | null,
): ReactNode | null {
  // A subagent spawn: its card, with the way into it.
  const spawn = agents?.find((a) => a.span_id === ctx.sourceSpanId);
  if (spawn) {
    const parent = agents?.find((a) => a.span_id === spawn.parent_span_id);
    const report = ctx.finalReply ?? spawnResult(ctx.attributes);
    return (
      <div className="p-4">
        <SubagentCard
          agent={spawn}
          turnLabel={spawn.turn_index === null ? "no turn" : `Turn ${spawn.turn_index + 1}`}
          parentLabel={parent ? (parent.description ?? "a subagent") : "the main agent"}
          brief={ctx.attributes ? spawnBrief(ctx.attributes) : undefined}
          report={ctx.finalReply === undefined && report === null ? undefined : report}
          action={
            spawn.linked && nav.openAgent ? (
              <Button size="xs" variant="outline" onClick={() => nav.openAgent?.(spawn.span_id)}>
                <SubagentIcon /> Open subagent
              </Button>
            ) : !spawn.linked ? (
              <span className="text-xs text-muted-foreground">transcript not uploaded</span>
            ) : null
          }
        />
      </div>
    );
  }
  if (ctx.attributes?.["converted.synthesized_root"] === true) {
    // The session root: trace totals (the analysis is in its own panel).
    const facts: [string, string, string?][] = [
      ["Duration", formatDuration(trace.duration_ms)],
      ["Turns", String(trace.analysis.session.turn_count)],
      ["Spans", trace.span_count.toLocaleString()],
      [
        "Tokens (incl. cached)",
        trace.total_tokens !== null ? formatCompact(trace.total_tokens) : "—",
        trace.total_tokens?.toLocaleString(),
      ],
      ["Span errors", trace.error_count.toLocaleString()],
      ["Subagents", String(trace.subagents?.count ?? 0)],
    ];
    return (
      <div className="flex flex-col gap-4 p-4">
        <h3 className="text-sm font-semibold">Session</h3>
        <dl className="grid grid-cols-3 gap-x-4 gap-y-2">
          {facts.map(([k, v, exact]) => (
            <div key={k}>
              <dt className="text-xs text-muted-foreground">{k}</dt>
              <dd className="font-mono text-xs" title={exact}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
        <Block title="Tools">
          <ExpandableText
            text={trace.tool_names.length ? trace.tool_names.join(", ") : "—"}
            lines={2}
            className="mt-0.5 text-xs"
          />
        </Block>
        {trace.skill_names && trace.skill_names.length > 0 && (
          <Block title="Skills">
            <p className="mt-0.5 text-xs">{trace.skill_names.join(", ")}</p>
          </Block>
        )}
      </div>
    );
  }
  const turnIndex = turnIndexOf(ctx);
  if (turnIndex === null) return null;

  const turn = trace.analysis.turns.find((t) => t.turn_index === turnIndex);
  const ask = ctx.attributes?.["turn.user_message"];
  const askText = typeof ask === "string" ? stripWrappers(ask) || ask : null;
  const automated = ctx.attributes?.["turn.origin"] === "automated";
  const invoked = (trace.skills ?? [])
    .filter((u) => u.turn_index === turnIndex && u.source === "user")
    .map((u) => u.name);

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">Turn {turnIndex + 1}</h3>
        {turn?.outcome && <OutcomeBadge outcome={turn.outcome} />}
        {automated && <AutomatedMarker />}
      </div>
      {invoked.length > 0 && (
        <p className="text-sm">
          <span className="text-muted-foreground">Invoked skill: </span>
          {invoked.map((name) => `/${name}`).join(", ")}
        </p>
      )}
      <Block title={automated ? "Event" : "Asked"}>
        {askText ? (
          <ClampedText text={askText} lines={6} />
        ) : (
          <p className="mt-0.5 text-sm text-muted-foreground">
            {ctx.attributes === null ? "Loading…" : "Not recorded."}
          </p>
        )}
      </Block>
      <Block title="Final reply">
        {ctx.finalReply ? (
          // The conversation's renderer (light markdown, tables, pasted folds).
          <div className="mt-0.5">
            <MessageText text={ctx.finalReply} />
          </div>
        ) : (
          <p className="mt-0.5 text-sm text-muted-foreground">
            {ctx.finalReply === undefined ? "Loading…" : "No reply recorded."}
          </p>
        )}
      </Block>
      <Block title="Analysis">
        <div className="mt-1">
          {turn ? (
            <TurnDetailBody
              trace={trace}
              turn={turn}
              nav={nav}
              onAnalysisChange={onAnalysisChange}
            />
          ) : (
            <p className="text-sm text-muted-foreground">This turn has not been judged yet.</p>
          )}
        </div>
      </Block>
    </div>
  );
}

/** A spawn's tool result, unless it is only the background-launch notice. */
function spawnResult(attributes: Record<string, unknown> | null): string | null {
  const result = attributes?.["gen_ai.tool.call.result"];
  if (typeof result !== "string" || !result || /^Async agent launched/.test(result)) return null;
  return result;
}
