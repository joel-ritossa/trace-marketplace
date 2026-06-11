"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pager, usePageParam } from "@/components/shell/pager";
import { UploadsTable } from "@/components/uploads/uploads-table";
import { listUploads, type UploadList } from "@/lib/api/uploads";
import { useRealtimeRefetch } from "@/lib/realtime";

const PAGE_SIZE = 25;

export default function UploadsPage() {
  const [result, setResult] = useState<UploadList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { page, setPage } = usePageParam();

  const reload = useCallback(() => {
    listUploads(PAGE_SIZE, (page - 1) * PAGE_SIZE)
      .then((res) => {
        setResult(res);
        setError(null);
      })
      .catch(() => setError("Could not load uploads. Check the API is running."));
  }, [page]);

  useEffect(reload, [reload]);
  // Rows flip received → processing → complete/failed while a CLI sync runs;
  // realtime events just trigger a refetch (invalidation only).
  useRealtimeRefetch("uploads", reload);

  // Out-of-range page (URL-edited or the list shrank): snap to the last page
  // instead of rendering a false empty state.
  useEffect(() => {
    if (result && result.uploads.length === 0 && page > 1 && result.total > 0) {
      setPage(Math.max(1, Math.ceil(result.total / PAGE_SIZE)));
    }
  }, [result, page, setPage]);

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Uploads</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every file you’ve uploaded — from the web or the sync CLI — with its ingestion result.
      </p>

      <div className="mt-6">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : result === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : result.uploads.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <FileUp className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No uploads yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload a file on the web or sync a directory with the CLI.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/upload">Upload a trace</Link>
            </Button>
          </div>
        ) : (
          <>
            <UploadsTable uploads={result.uploads} />
            <div className="mt-4">
              <Pager
                page={page}
                pageSize={PAGE_SIZE}
                total={result.total}
                onPageChange={setPage}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
