"use client";

import { SearchX, Store } from "lucide-react";
import { Pager } from "@/components/shell/pager";
import { BulkAcquireAction } from "@/components/traces/bulk-actions";
import { BulkBar, useSelection } from "@/components/traces/bulk-bar";
import { ExcludedNote } from "@/components/traces/excluded-note";
import { SaveSubscription } from "@/components/traces/save-subscription";
import { TraceList } from "@/components/traces/trace-list";
import { TraceFiltersBar, hasActiveFilters } from "@/components/traces/trace-filters";
import { useTraceList } from "@/components/traces/use-trace-list";

export default function MarketplacePage() {
  const { result, error, filters, setFilters, sort, setSort, page, setPage, pageSize, setPageSize, reload } =
    useTraceList("marketplace");
  const { selected, toggle, setAll, clear } = useSelection();
  const filtered = hasActiveFilters(filters);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Browse</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Listed agent traces from every contributor. Inspect freely; acquire to download.
          </p>
        </div>
        <SaveSubscription filters={filters} total={result?.total ?? null} />
      </div>

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
              Nothing matches the current search and filters.
            </p>
            <ExcludedNote count={result.excluded_unanalyzed} className="mt-2" />
          </div>
        ) : result.traces.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <Store className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">The marketplace is empty</p>
            <p className="mt-1 text-sm text-muted-foreground">
              No one has listed a trace yet. List one of yours from its detail page.
            </p>
          </div>
        ) : (
          <>
            <ExcludedNote count={result.excluded_unanalyzed} className="mb-2" />
            <TraceList
              traces={result.traces}
              view="marketplace"
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
            <BulkBar count={selected.size} onClear={clear}>
              <BulkAcquireAction
                ids={[...selected]}
                onDone={() => {
                  clear();
                  reload();
                }}
              />
            </BulkBar>
          </>
        )}
      </div>
    </div>
  );
}
