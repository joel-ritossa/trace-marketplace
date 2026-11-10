import { TraceInspector } from "@/components/traces/trace-inspector";

export default async function TraceDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ traceId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { traceId } = await params;
  // ?turn=N focuses that turn's row in the Analysis section (review links).
  // ?span=<source span id> selects that span in the evidence tree, as an
  // evidence click does (pill popovers on list pages link here).
  // ?agent=<spawn span id> scopes the evidence to a subagent; ?view= picks
  // the evidence view (conversation | spans | agents).
  const { turn, span, agent, view } = await searchParams;
  const focusTurn = typeof turn === "string" && /^\d+$/.test(turn) ? Number(turn) : undefined;
  const focusSpan = typeof span === "string" && span ? span : undefined;
  // Full content width by design (4_pages.md): the tree + detail panel get the room.
  const focusAgent = typeof agent === "string" && agent ? agent : undefined;
  const initialView = view === "spans" || view === "agents" ? view : undefined;
  return (
    <TraceInspector
      traceId={traceId}
      focusTurn={focusTurn}
      focusSpan={focusSpan}
      focusAgent={focusAgent}
      initialView={initialView}
    />
  );
}
