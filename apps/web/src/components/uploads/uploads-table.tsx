"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/uploads/status-badge";
import { downloadUpload } from "@/lib/api/uploads";
import type { UploadListItem } from "@/lib/api/uploads";
import { formatDate } from "@/lib/format";
import { cleanName, traceTitle } from "@/components/traces/names";
import { cn } from "@/lib/utils";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const MAX_TRACE_LINKS = 3;

// Placeholder kinds from the redaction ruleset (services/api/app/redaction.py).
const REDACTION_LABELS: Record<string, [string, string]> = {
  EMAIL: ["email", "emails"],
  PHONE: ["phone number", "phone numbers"],
  CREDIT_CARD: ["card number", "card numbers"],
  SSN: ["SSN", "SSNs"],
  IP: ["IP address", "IP addresses"],
  API_KEY: ["API key", "API keys"],
  JWT: ["token", "tokens"],
  PRIVATE_KEY: ["private key", "private keys"],
  SECRET: ["secret", "secrets"],
};

/** Masked values as one total, the per-kind breakdown on hover. */
function RedactionTotal({ counts }: { counts: Record<string, number> | null }) {
  const entries = Object.entries(counts ?? {}).filter(([, n]) => n > 0);
  if (entries.length === 0) return null;
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  const detail = entries
    .map(([kind, n]) => {
      const [one, many] = REDACTION_LABELS[kind] ?? [kind, kind];
      return `${n} ${n === 1 ? one : many}`;
    })
    .join(", ");
  return (
    <span className="whitespace-nowrap text-xs text-muted-foreground" title={`Masked: ${detail}`}>
      {total.toLocaleString()} masked
    </span>
  );
}

function TraceLinks({
  traceIds,
  traces,
}: {
  traceIds: string[];
  traces?: UploadListItem["traces"];
}) {
  if (traceIds.length === 0)
    return (
      <span
        className="text-muted-foreground"
        title="No current traces — superseded by a newer sync of this file, or nothing was parsed"
      >
        —
      </span>
    );
  return (
    <span className="flex flex-wrap gap-x-2">
      {traceIds.slice(0, MAX_TRACE_LINKS).map((id) => {
        // Named when the API sends titles; the short id otherwise.
        const named = traces?.find((t) => t.trace_id === id);
        return (
          <Link
            key={id}
            href={`/traces/${id}`}
            title={named ? `First ask: ${cleanName(named.name)}` : id}
            className={cn(
              "underline underline-offset-2 hover:text-foreground",
              named ? "block max-w-64 truncate text-xs" : "font-mono text-xs",
            )}
          >
            {named ? traceTitle(named.name, named.goal) : id.slice(0, 8)}
          </Link>
        );
      })}
      {traceIds.length > MAX_TRACE_LINKS && (
        <span className="text-xs text-muted-foreground">
          +{traceIds.length - MAX_TRACE_LINKS} more
        </span>
      )}
    </span>
  );
}

// Low-value columns drop below xl so the table fits beside the icon rail.
const WIDE_ONLY = "hidden xl:table-cell";

/** Re-syncs of the same session file share a filename: one group per file,
 *  newest first (the list's order), older syncs folded under it. */
function groupByFile(uploads: UploadListItem[]): UploadListItem[][] {
  const groups = new Map<string, UploadListItem[]>();
  for (const upload of uploads) {
    const group = groups.get(upload.filename);
    if (group) group.push(upload);
    else groups.set(upload.filename, [upload]);
  }
  return [...groups.values()];
}

export function UploadsTable({ uploads }: { uploads: UploadListItem[] }) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  async function onDownload(upload: UploadListItem) {
    setDownloading(upload.upload_id);
    setDownloadError(null);
    try {
      await downloadUpload(upload.upload_id, upload.filename);
    } catch {
      setDownloadError(`Download of ${upload.filename} failed. Try again.`);
    }
    setDownloading(null);
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-background">
      {downloadError && (
        <p className="border-b px-4 py-2 text-xs text-error-deep">{downloadError}</p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">File</th>
            <th className={cn("px-4 py-2.5 font-medium", WIDE_ONLY)}>Size</th>
            <th className={cn("px-4 py-2.5 font-medium", WIDE_ONLY)}>Source</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Traces</th>
            <th className="px-4 py-2.5 font-medium">Uploaded</th>
            <th className={cn("px-4 py-2.5 font-medium", WIDE_ONLY)}>Processed</th>
            <th className="px-4 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {groupByFile(uploads).map((group) => {
            const [latest, ...older] = group;
            const open = expanded.has(latest.filename);
            return [latest, ...(open ? older : [])].map((upload, i) => (
              <UploadRow
                key={upload.upload_id}
                upload={upload}
                older={i > 0}
                downloading={downloading === upload.upload_id}
                onDownload={() => onDownload(upload)}
                toggle={
                  i === 0 && older.length > 0
                    ? {
                        open,
                        count: older.length,
                        onToggle: () =>
                          setExpanded((prev) => {
                            const next = new Set(prev);
                            if (!next.delete(latest.filename)) next.add(latest.filename);
                            return next;
                          }),
                      }
                    : undefined
                }
              />
            ));
          })}
        </tbody>
      </table>
    </div>
  );
}

function UploadRow({
  upload,
  older,
  downloading,
  onDownload,
  toggle,
}: {
  upload: UploadListItem;
  older: boolean;
  downloading: boolean;
  onDownload: () => void;
  toggle?: { open: boolean; count: number; onToggle: () => void };
}) {
  return (
    <tr className={cn("border-b last:border-b-0", older && "bg-canvas-soft text-muted-foreground")}>
      <td className="max-w-72 px-4 py-2.5">
        <span className={cn("block truncate", older ? "pl-4 text-xs" : "font-medium")} title={upload.filename}>
          {upload.filename}
        </span>
        {toggle && (
          <button
            type="button"
            onClick={toggle.onToggle}
            aria-expanded={toggle.open}
            className="mt-0.5 inline-flex items-center gap-1 rounded-sm text-xs text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <ChevronRight className={cn("size-3 transition-transform", toggle.open && "rotate-90")} />
            {toggle.count} older sync{toggle.count === 1 ? "" : "s"}
          </button>
        )}
      </td>
      <td className={cn("whitespace-nowrap px-4 py-2.5 font-mono text-xs text-muted-foreground", WIDE_ONLY)}>
        {formatBytes(upload.size_bytes)}
      </td>
      <td className={cn("px-4 py-2.5", WIDE_ONLY)}>
        <span className="rounded-md border px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
          {upload.source}
        </span>
      </td>
      <td className="px-4 py-2.5">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <StatusBadge status={upload.status} />
          <RedactionTotal counts={upload.redaction_counts} />
        </span>
        {upload.status === "failed" && upload.error_message && (
          <p className="mt-1 max-w-90 text-xs text-error-deep">{upload.error_message}</p>
        )}
      </td>
      <td className="px-4 py-2.5">
        <TraceLinks traceIds={upload.trace_ids} traces={upload.traces} />
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-muted-foreground">
        {formatDate(upload.created_at)}
      </td>
      <td className={cn("whitespace-nowrap px-4 py-2.5 font-mono text-xs text-muted-foreground", WIDE_ONLY)}>
        {upload.processed_at ? formatDate(upload.processed_at) : "—"}
      </td>
      <td className="px-4 py-2.5 text-right">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Download ${upload.filename}`}
          disabled={downloading}
          onClick={onDownload}
        >
          <Download />
        </Button>
      </td>
    </tr>
  );
}
