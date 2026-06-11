"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/uploads/status-badge";
import { downloadUpload } from "@/lib/api/uploads";
import type { UploadListItem } from "@/lib/api/uploads";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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
    } finally {
      setDownloading(null);
    }
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
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Uploaded</th>
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
                <StatusBadge status={upload.status} />
                {upload.status === "failed" && upload.error_message && (
                  <p className="mt-1 max-w-90 text-xs text-error-deep">{upload.error_message}</p>
                )}
              </td>
              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                {formatDate(upload.created_at)}
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
