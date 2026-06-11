"use client";

import { Pager } from "@/components/shell/pager";
import { BulkDownloadAction } from "@/components/traces/bulk-actions";
import { BulkBar, useSelection } from "@/components/traces/bulk-bar";
import { ExcludedNote } from "@/components/traces/excluded-note";
import { TraceFiltersBar, hasActiveFilters } from "@/components/traces/trace-filters";
import { TraceList } from "@/components/traces/trace-list";
import { useTraceList } from "@/components/traces/use-trace-list";
import { Button } from "@/components/ui/button";
import { BookMarked, SearchX } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

export default function LibraryPage() {
  const { result, error, filters, setFilters, sort, setSort, page, setPage, pageSize, setPageSize } =
    useTraceList("acquired");
  const { selected, toggle, setAll, clear } = useSelection();
  const [bulkError, setBulkError] = useState<string | null>(null);
  const filtered = hasActiveFilters(filters);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Traces you have acquired, ready to download.
      </p>

      <div className="mt-6">
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
              Nothing saved matches the current search and filters.
            </p>
            <ExcludedNote count={result.excluded_unanalyzed} className="mt-2" />
          </div>
        ) : result.traces.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <BookMarked className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">Your library is empty</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Acquire traces from the marketplace and they will appear here.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/marketplace">Browse the marketplace</Link>
            </Button>
          </div>
        ) : (
          <>
            <ExcludedNote count={result.excluded_unanalyzed} className="mb-2" />
            <TraceList
              traces={result.traces}
              view="library"
              selection={{ selected, toggle, setAll }}
            />
            <div className="mt-4">
              <Pager
                page={page}
                pageSize={pageSize}
                total={result.total}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
              />
            </div>
            <BulkBar count={selected.size} onClear={clear} status={bulkError}>
              <BulkDownloadAction ids={[...selected]} onError={setBulkError} />
            </BulkBar>
          </>
        )}
      </div>
    </div>
  );
}
