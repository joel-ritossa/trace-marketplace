"use client";

import { useState } from "react";
import Link from "next/link";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/uploads/status-badge";
import { downloadUpload } from "@/lib/api/uploads";
import type { UploadListItem } from "@/lib/api/uploads";
import { formatDate } from "@/lib/format";

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

function redactionSummary(counts: Record<string, number> | null): string | null {
  if (!counts) return null;
  const parts = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([kind, n]) => {
      const [one, many] = REDACTION_LABELS[kind] ?? [kind, kind];
      return `${n} ${n === 1 ? one : many}`;
    });
  return parts.length > 0 ? `${parts.join(", ")} masked` : null;
}

function TraceLinks({ traceIds }: { traceIds: string[] }) {
  if (traceIds.length === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="flex flex-wrap gap-x-2">
      {traceIds.slice(0, MAX_TRACE_LINKS).map((id) => (
        <Link
          key={id}
          href={`/traces/${id}`}
          className="font-mono text-xs underline underline-offset-2 hover:text-foreground"
        >
          {id.slice(0, 8)}
        </Link>
      ))}
      {traceIds.length > MAX_TRACE_LINKS && (
        <span className="text-xs text-muted-foreground">
          +{traceIds.length - MAX_TRACE_LINKS} more
        </span>
      )}
    </span>
  );
}

export function UploadsTable({ uploads }: { uploads: UploadListItem[] }) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

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
            <th className="px-4 py-2.5 font-medium">Size</th>
            <th className="px-4 py-2.5 font-medium">Source</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Traces</th>
            <th className="px-4 py-2.5 font-medium">Uploaded</th>
            <th className="px-4 py-2.5 font-medium">Processed</th>
            <th className="px-4 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {uploads.map((upload) => (
            <tr key={upload.upload_id} className="border-b last:border-b-0">
              <td className="max-w-60 truncate px-4 py-2.5 font-medium">{upload.filename}</td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {formatBytes(upload.size_bytes)}
              </td>
              <td className="px-4 py-2.5">
                <span className="rounded-md border px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                  {upload.source}
                </span>
              </td>
              <td className="px-4 py-2.5">
                <StatusBadge status={upload.status} />
                {upload.status === "failed" && upload.error_message && (
                  <p className="mt-1 max-w-90 text-xs text-error-deep">{upload.error_message}</p>
                )}
                {redactionSummary(upload.redaction_counts) && (
                  <p className="mt-1 max-w-90 text-xs text-muted-foreground">
                    {redactionSummary(upload.redaction_counts)}
                  </p>
                )}
              </td>
              <td className="px-4 py-2.5">
                <TraceLinks traceIds={upload.trace_ids} />
              </td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {formatDate(upload.created_at)}
              </td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {upload.processed_at ? formatDate(upload.processed_at) : "—"}
              </td>
              <td className="px-4 py-2.5 text-right">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Download ${upload.filename}`}
                  disabled={downloading === upload.upload_id}
                  onClick={() => onDownload(upload)}
                >
                  <Download />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
