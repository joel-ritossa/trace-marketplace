"use client";

import Link from "next/link";
import { AlertCircle, ArrowRight, CheckCircle2, TriangleAlert } from "lucide-react";
import type { Flow } from "@/components/uploads/upload-flow";

export function FlowStatus({ flow }: { flow: Flow }) {
  if (flow.phase === "idle") return null;

  if (flow.phase === "uploading" || flow.phase === "tracking") {
    const label =
      flow.phase === "uploading"
        ? `Uploading ${flow.filename}…`
        : flow.upload.status === "received"
          ? "Received — waiting for a worker…"
          : "Processing…";
    return (
      <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
        <span className="size-3 animate-spin rounded-full border-2 border-border border-t-foreground" />
        {label}
      </p>
    );
  }

  if (flow.phase === "rejected") {
    return (
      <p className="mt-3 flex items-center gap-2 text-sm text-error-deep">
        <AlertCircle className="size-4 shrink-0" />
        {flow.message}
      </p>
    );
  }

  const { upload } = flow;
  if (upload.status === "failed") {
    return (
      <p className="mt-3 flex items-center gap-2 text-sm text-error-deep">
        <AlertCircle className="size-4 shrink-0" />
        {upload.error_message ?? "Ingestion failed."}
      </p>
    );
  }
  // parse_warnings shape: { skipped_spans: N, samples: [...] } — the count is
  // user-facing; the samples are debugging detail left to the API response.
  const skipped = upload.parse_warnings?.skipped_spans;
  return (
    <div className="mt-3 flex flex-col gap-1">
      <p className="flex items-center gap-2 text-sm text-status-ok">
        <CheckCircle2 className="size-4 shrink-0" />
        {upload.filename} ingested.
      </p>
      {typeof skipped === "number" && skipped > 0 && (
        <p className="flex items-center gap-2 text-sm text-warning-deep">
          <TriangleAlert className="size-4 shrink-0" />
          {skipped} malformed span{skipped === 1 ? "" : "s"} skipped.
        </p>
      )}
      {upload.trace_ids.length > 0 && (
        <p className="flex items-center gap-2 text-sm">
          <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
          {upload.trace_ids.length === 1 ? (
            <Link href={`/traces/${upload.trace_ids[0]}`} className="font-medium hover:underline">
              View the trace
            </Link>
          ) : (
            <span className="flex flex-wrap gap-x-2">
              {upload.trace_ids.map((traceId, i) => (
                <Link
                  key={traceId}
                  href={`/traces/${traceId}`}
                  className="font-medium hover:underline"
                >
                  Trace {i + 1}
                </Link>
              ))}
            </span>
          )}
        </p>
      )}
    </div>
  );
}
