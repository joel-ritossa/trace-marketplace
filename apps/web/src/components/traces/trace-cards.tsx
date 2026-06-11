"use client";

import Link from "next/link";
import { useState } from "react";
import { Download } from "lucide-react";
import { LibraryBadge, VisibilityBadge } from "@/components/traces/badges";
import { Button } from "@/components/ui/button";
import { downloadTrace, type TraceListItem } from "@/lib/api/traces";
import { formatDate, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

function CardMeta({ trace }: { trace: TraceListItem }) {
  const parts = [
    `${trace.span_count} spans`,
    trace.error_count > 0 ? `${trace.error_count} errors` : null,
    formatDuration(trace.duration_ms),
    trace.model,
  ].filter(Boolean);
  return (
    <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{parts.join(" · ")}</p>
  );
}

/** Result card list for /marketplace and /library (4_pages.md). */
export function TraceCards({
  traces,
  context,
}: {
  traces: TraceListItem[];
  context: "marketplace" | "library";
}) {
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function onDownload(trace: TraceListItem) {
    setDownloadError(null);
    try {
      await downloadTrace(trace.trace_id, `${trace.name.replaceAll("/", "_")}.json`);
    } catch {
      setDownloadError(trace.trace_id);
    }
  }

  return (
    <ul className="flex flex-col gap-3">
      {traces.map((trace) => (
        <li
          key={trace.trace_id}
          className="rounded-lg border bg-background px-4 py-3 transition-colors hover:bg-accent/30"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "size-2 shrink-0 rounded-full",
                    trace.status === "error" ? "bg-error-deep" : "bg-status-ok",
                  )}
                />
                <Link
                  href={`/traces/${trace.trace_id}`}
                  className="truncate text-sm font-medium hover:underline"
                >
                  {trace.name}
                </Link>
                {context === "marketplace" && trace.acquired && <LibraryBadge />}
                {trace.is_owner && <VisibilityBadge visibility={trace.visibility} />}
              </div>
              <CardMeta trace={trace} />
              {trace.description && (
                <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
                  {trace.description}
                </p>
              )}
              {trace.tags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {trace.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-col items-end gap-1.5 text-right">
              <p className="text-xs text-muted-foreground">
                {trace.owner_display_name ?? "unknown contributor"}
              </p>
              <p className="font-mono text-xs text-muted-foreground">
                {context === "library" && trace.acquired_at
                  ? `acquired ${formatDate(trace.acquired_at)}`
                  : trace.listed_at
                    ? `listed ${formatDate(trace.listed_at)}`
                    : null}
              </p>
              {context === "library" && (
                <Button size="sm" variant="outline" onClick={() => onDownload(trace)}>
                  <Download /> Download
                </Button>
              )}
              {downloadError === trace.trace_id && (
                <p className="text-xs text-error-deep">Download failed — try again.</p>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
