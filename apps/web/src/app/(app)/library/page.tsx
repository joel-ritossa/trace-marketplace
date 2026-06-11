"use client";

import Link from "next/link";
import { BookMarked } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pager } from "@/components/shell/pager";
import { TraceCards } from "@/components/traces/trace-cards";
import { TRACE_PAGE_SIZE, useTraceList } from "@/components/traces/use-trace-list";

export default function LibraryPage() {
  const { result, error, page, setPage } = useTraceList("acquired");

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">My Library</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Traces you have acquired, ready to download.
      </p>

      <div className="mt-6">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : result === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
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
            <TraceCards traces={result.traces} context="library" />
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
