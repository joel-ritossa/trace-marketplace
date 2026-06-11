"use client";

import Link from "next/link";
import { AlertCircle, ArrowRight, CheckCircle2, TriangleAlert } from "lucide-react";
import type { FileFlow } from "@/components/uploads/upload-flow";

function Spinner() {
  return (
    <span className="size-3 shrink-0 animate-spin rounded-full border-2 border-border border-t-foreground" />
  );
}

/** One dropped file's live status: real reasons verbatim, links to the
 *  created traces on success (4_pages.md /uploads). */
export function FileStatusRow({ flow }: { flow: FileFlow }) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      <span className="max-w-64 truncate font-medium" title={flow.filename}>
        {flow.filename}
      </span>
      <Status flow={flow} />
    </li>
  );
}

function Status({ flow }: { flow: FileFlow }) {
  if (flow.phase === "queued") {
    return <span className="text-muted-foreground">Queued…</span>;
  }
  if (flow.phase === "uploading") {
    return (
      <span className="flex items-center gap-2 text-muted-foreground">
        <Spinner /> Uploading…
      </span>
    );
  }
  if (flow.phase === "rejected") {
    return (
      <span className="flex items-center gap-2 text-error-deep">
        <AlertCircle className="size-4 shrink-0" />
        {flow.message}
      </span>
    );
  }
  if (flow.phase === "tracking") {
    return (
      <span className="flex items-center gap-2 text-muted-foreground">
        <Spinner />
        {flow.upload.status === "received" ? "Received — waiting for a worker…" : "Processing…"}
      </span>
    );
  }

  const { upload } = flow;
  if (upload.status === "failed") {
    return (
      <span className="flex items-center gap-2 text-error-deep">
        <AlertCircle className="size-4 shrink-0" />
        {upload.error_message ?? "Ingestion failed."}
      </span>
    );
  }
  // parse_warnings shape: { skipped_spans: N, samples: [...] } — the count is
  // user-facing; the samples are debugging detail left to the API response.
  const skipped = upload.parse_warnings?.skipped_spans;
  return (
    <>
      <span className="flex items-center gap-1.5 text-status-ok">
        <CheckCircle2 className="size-4 shrink-0" /> Ingested
      </span>
      {typeof skipped === "number" && skipped > 0 && (
        <span className="flex items-center gap-1.5 text-warning-deep">
          <TriangleAlert className="size-4 shrink-0" />
          {skipped} malformed span{skipped === 1 ? "" : "s"} skipped
        </span>
      )}
      {upload.trace_ids.length > 0 && (
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
          {upload.trace_ids.length === 1 ? (
            <Link href={`/traces/${upload.trace_ids[0]}`} className="font-medium hover:underline">
              View the trace
            </Link>
          ) : (
            upload.trace_ids.map((traceId, i) => (
              <Link key={traceId} href={`/traces/${traceId}`} className="font-medium hover:underline">
                Trace {i + 1}
              </Link>
            ))
          )}
        </span>
      )}
    </>
  );
}
