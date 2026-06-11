import { TraceInspector } from "@/components/traces/trace-inspector";

export default async function TraceDetailPage({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = await params;
  // Full content width by design (4_pages.md): the tree + detail panel get the room.
  return <TraceInspector traceId={traceId} />;
}
