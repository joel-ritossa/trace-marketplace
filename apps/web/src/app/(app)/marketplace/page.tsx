"use client";

import { SearchX, Store } from "lucide-react";
import { TraceCards } from "@/components/traces/trace-cards";
import { TraceFiltersBar, hasActiveFilters } from "@/components/traces/trace-filters";
import { useTraceList } from "@/components/traces/use-trace-list";

export default function MarketplacePage() {
  const { result, error, filters, setFilters, sort, setSort } = useTraceList("marketplace");
  const filtered = hasActiveFilters(filters);

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Marketplace</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Listed agent traces from every contributor. Inspect freely; acquire to download.
      </p>

      <div className="mt-6">
        <TraceFiltersBar onChange={setFilters} sort={sort} onSortChange={setSort} />
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
          <TraceCards traces={result.traces} context="marketplace" />
        )}
      </div>
    </div>
  );
}
