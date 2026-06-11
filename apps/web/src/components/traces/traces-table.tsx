"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { formatDate, formatDuration } from "@/lib/format";
import { VisibilityBadge } from "@/components/traces/badges";
import type { TraceListItem } from "@/lib/api/traces";

function StatusDot({ status }: { status: TraceListItem["status"] }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "size-2 rounded-full",
          status === "error" ? "bg-error-deep" : "bg-status-ok",
        )}
      />
      <span className="text-xs text-muted-foreground">{status}</span>
    </span>
  );
}

export function TracesTable({ traces }: { traces: TraceListItem[] }) {
  return (
    <div className="overflow-hidden rounded-lg border bg-background">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Name</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Spans</th>
            <th className="px-4 py-2.5 font-medium">Errors</th>
            <th className="px-4 py-2.5 font-medium">Duration</th>
            <th className="px-4 py-2.5 font-medium">Model</th>
            <th className="px-4 py-2.5 font-medium">Visibility</th>
            <th className="px-4 py-2.5 font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {traces.map((trace) => (
            <tr key={trace.trace_id} className="border-b transition-colors last:border-b-0 hover:bg-accent/50">
              <td className="max-w-72 px-4 py-2.5">
                <Link
                  href={`/traces/${trace.trace_id}`}
                  className="block truncate font-medium hover:underline"
                >
                  {trace.name}
                </Link>
              </td>
              <td className="px-4 py-2.5">
                <StatusDot status={trace.status} />
              </td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {trace.span_count}
              </td>
              <td
                className={cn(
                  "px-4 py-2.5 font-mono text-xs",
                  trace.error_count > 0 ? "text-error-deep" : "text-muted-foreground",
                )}
              >
                {trace.error_count}
              </td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {formatDuration(trace.duration_ms)}
              </td>
              <td className="max-w-48 truncate px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {trace.model ?? "—"}
              </td>
              <td className="px-4 py-2.5">
                <VisibilityBadge visibility={trace.visibility} />
              </td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {formatDate(trace.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
