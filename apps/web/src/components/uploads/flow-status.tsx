"use client";

import { AlertCircle, CheckCircle2, TriangleAlert } from "lucide-react";
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
  const warnings = upload.parse_warnings ? Object.entries(upload.parse_warnings) : [];
  return (
    <div className="mt-3 flex flex-col gap-1">
      <p className="flex items-center gap-2 text-sm text-status-ok">
        <CheckCircle2 className="size-4 shrink-0" />
        {upload.filename} ingested.
      </p>
      {warnings.length > 0 && (
        <p className="flex items-center gap-2 text-sm text-warning-deep">
          <TriangleAlert className="size-4 shrink-0" />
          {warnings.map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`).join(", ")}
        </p>
      )}
    </div>
  );
}
