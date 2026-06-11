"use client";

import { useCallback, useEffect, useState } from "react";
import { FileUp } from "lucide-react";
import { Pager, usePageParam } from "@/components/shell/pager";
import { WorkspaceTabs } from "@/components/traces/workspace-tabs";
import { UploadFlow } from "@/components/uploads/upload-flow";
import { UploadsTable } from "@/components/uploads/uploads-table";
import { listUploads, type UploadList } from "@/lib/api/uploads";
import { useRealtimeRefetch } from "@/lib/realtime";

/** The single ingest surface (4_pages.md): dropzone band on top, full
 *  history below. Web drops and CLI syncs land in the same table. */
export default function UploadsPage() {
  const [result, setResult] = useState<UploadList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { page, setPage, pageSize, setPageSize } = usePageParam();

  const reload = useCallback(() => {
    listUploads(pageSize, (page - 1) * pageSize)
      .then((res) => {
        setResult(res);
        setError(null);
      })
      .catch(() => setError("Could not load uploads. Check the API is running."));
  }, [page, pageSize]);

  useEffect(reload, [reload]);
  // Rows flip received → processing → complete/failed while a CLI sync runs;
  // realtime events just trigger a refetch (invalidation only).
  useRealtimeRefetch("uploads", reload);

  // Out-of-range page (URL-edited or the list shrank): snap to the last page
  // instead of rendering a false empty state.
  useEffect(() => {
    if (result && result.uploads.length === 0 && page > 1 && result.total > 0) {
      setPage(Math.max(1, Math.ceil(result.total / pageSize)));
    }
  }, [result, page, pageSize, setPage]);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <h1 className="text-2xl font-semibold tracking-tight">Traces</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Contribute trace files and follow every upload — web or sync CLI — through ingestion.
      </p>

      <div className="mt-5">
        <WorkspaceTabs active="/uploads" />
      </div>

      <div className="mt-5">
        <UploadFlow onChanged={reload} />
      </div>

      <div className="mt-8">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : result === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : result.uploads.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <FileUp className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No uploads yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Drop files above or sync a directory with the CLI.
            </p>
          </div>
        ) : (
          <>
            <UploadsTable uploads={result.uploads} />
            <div className="mt-4">
              <Pager
                page={page}
                pageSize={pageSize}
                total={result.total}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
