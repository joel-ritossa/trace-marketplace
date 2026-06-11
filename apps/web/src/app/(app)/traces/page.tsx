"use client";

import Link from "next/link";
import { useState } from "react";
import { ScrollText, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pager } from "@/components/shell/pager";
import { BulkVisibilityActions } from "@/components/traces/bulk-actions";
import { BulkBar, useSelection } from "@/components/traces/bulk-bar";
import { ExcludedNote } from "@/components/traces/excluded-note";
import { TraceList } from "@/components/traces/trace-list";
import { WorkspaceTabs } from "@/components/traces/workspace-tabs";
import { TraceFiltersBar, hasActiveFilters } from "@/components/traces/trace-filters";
import { useTraceList } from "@/components/traces/use-trace-list";

export default function TracesPage() {
  const { result, error, filters, setFilters, sort, setSort, page, setPage, pageSize, setPageSize, reload } =
    useTraceList("mine");
  const { selected, toggle, setAll, clear } = useSelection();
  const [bulkStatus, setBulkStatus] = useState<string | null>(null);
  const filtered = hasActiveFilters(filters);

  // Bulk visibility changed rows server-side; re-run the current query.
  const onBulkDone = (summary: string) => {
    setBulkStatus(summary);
    clear();
    reload();
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <h1 className="text-2xl font-semibold tracking-tight">Traces</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Traces parsed from your uploads, private and listed.
      </p>

      <div className="mt-5">
        <WorkspaceTabs active="/traces" />
      </div>

      <div className="mt-5">
        <TraceFiltersBar
          filters={filters}
          onChange={setFilters}
          sort={sort}
          onSortChange={setSort}
        />
      </div>

      <div className="mt-4">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : result === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : result.traces.length === 0 && filtered ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <SearchX className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No traces match</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Nothing matches the current search and filters.
            </p>
            <ExcludedNote count={result.excluded_unanalyzed} className="mt-2" />
          </div>
        ) : result.traces.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <ScrollText className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No traces yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload a trace file and its parsed traces will appear here.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/uploads">Upload a trace</Link>
            </Button>
          </div>
        ) : (
          <>
            <ExcludedNote count={result.excluded_unanalyzed} className="mb-2" />
            <TraceList traces={result.traces} view="mine" selection={{ selected, toggle, setAll }} />
            <div className="mt-4">
              <Pager
                page={page}
                pageSize={pageSize}
                total={result.total}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
              />
            </div>
            <BulkBar count={selected.size} onClear={clear} status={bulkStatus}>
              <BulkVisibilityActions ids={[...selected]} onDone={onBulkDone} />
            </BulkBar>
          </>
        )}
      </div>
    </div>
  );
}
