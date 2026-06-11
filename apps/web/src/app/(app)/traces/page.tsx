"use client";

import Link from "next/link";
import { ScrollText, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pager } from "@/components/shell/pager";
import { TracesTable } from "@/components/traces/traces-table";
import { TraceFiltersBar, hasActiveFilters } from "@/components/traces/trace-filters";
import { TRACE_PAGE_SIZE, useTraceList } from "@/components/traces/use-trace-list";

export default function TracesPage() {
  const { result, error, filters, setFilters, sort, setSort, page, setPage } = useTraceList("mine");
  const filtered = hasActiveFilters(filters);

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">My Traces</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Traces parsed from{" "}
        <Link href="/uploads" className="underline underline-offset-2 hover:text-foreground">
          your uploads
        </Link>
        , private and listed.
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
            <ScrollText className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No traces yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload a trace file and its parsed traces will appear here.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/upload">Upload a trace</Link>
            </Button>
          </div>
        ) : (
          <>
            <TracesTable traces={result.traces} />
            <div className="mt-4">
              <Pager
                page={page}
                pageSize={TRACE_PAGE_SIZE}
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
