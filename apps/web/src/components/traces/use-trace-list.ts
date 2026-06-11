"use client";

import { useCallback, useEffect, useState } from "react";
import { usePageParam } from "@/components/shell/pager";
import {
  listTraces,
  type TraceFilters,
  type TraceList,
  type TraceScope,
  type TraceSort,
} from "@/lib/api/traces";

export const TRACE_PAGE_SIZE = 25;

/** Shared list-page state: scope + filters + sort + page (URL-backed) →
 *  result, reloading on change. Filter/sort changes reset to page 1. */
export function useTraceList(scope: TraceScope) {
  const [result, setResult] = useState<TraceList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFiltersState] = useState<TraceFilters>({});
  const [sort, setSortState] = useState<TraceSort>("created_at");
  const { page, setPage } = usePageParam();

  const setFilters = useCallback(
    (next: TraceFilters) => {
      setFiltersState(next);
      setPage(1);
    },
    [setPage],
  );

  const setSort = useCallback(
    (next: TraceSort) => {
      setSortState(next);
      setPage(1);
    },
    [setPage],
  );

  useEffect(() => {
    let cancelled = false;
    listTraces(scope, sort, filters, TRACE_PAGE_SIZE, (page - 1) * TRACE_PAGE_SIZE)
      .then((res) => {
        if (!cancelled) {
          setResult(res);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Could not load traces. Check the API is running.");
      });
    return () => {
      cancelled = true;
    };
  }, [scope, sort, filters, page]);

  // Out-of-range page (URL-edited or the list shrank): snap to the last page
  // instead of rendering a false empty state.
  useEffect(() => {
    if (result && result.traces.length === 0 && page > 1 && result.total > 0) {
      setPage(Math.max(1, Math.ceil(result.total / TRACE_PAGE_SIZE)));
    }
  }, [result, page, setPage]);

  return { result, error, filters, setFilters, sort, setSort, page, setPage };
}
