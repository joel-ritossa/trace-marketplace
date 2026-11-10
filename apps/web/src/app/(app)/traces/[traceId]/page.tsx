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
  const { turn } = await searchParams;
  const focusTurn = typeof turn === "string" && /^\d+$/.test(turn) ? Number(turn) : undefined;
  // Full content width by design (4_pages.md): the tree + detail panel get the room.
  return <TraceInspector traceId={traceId} focusTurn={focusTurn} />;
}
