import { TraceInspector } from "@/components/traces/trace-inspector";

export default async function TraceDetailPage({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = await params;
  return (
    // Break out of the layout's max-w-5xl: the tree + detail panel need room.
    <div className="relative left-1/2 w-screen max-w-screen -translate-x-1/2 px-6 xl:left-1/2 xl:w-[80rem] xl:max-w-[calc(100vw-2rem)]">
      <TraceInspector traceId={traceId} />
    </div>
  );
}
