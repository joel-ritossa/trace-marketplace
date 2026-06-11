"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { usePageParam } from "@/components/shell/pager";
import { filtersToParams, paramsToFilters } from "@/components/traces/filter-state";
import {
  listTraces,
  type TraceFilters,
  type TraceList,
  type TraceScope,
  type TraceSort,
} from "@/lib/api/traces";
import { useRealtimeRefetch } from "@/lib/realtime";

const SORTS: TraceSort[] = ["created_at", "duration_ms", "span_count"];

/** Shared list-page state. Filters + sort + page all live in the URL
 *  (4_pages.md cross-cutting: URL carries view state); changing filters or
 *  sort drops the page param, resetting to page 1. */
export function useTraceList(scope: TraceScope) {
  const [result, setResult] = useState<TraceList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { page, setPage, pageSize, setPageSize } = usePageParam();

  const filters = useMemo(() => paramsToFilters(searchParams), [searchParams]);
  const sortParam = searchParams.get("sort") as TraceSort | null;
  const sort: TraceSort = sortParam !== null && SORTS.includes(sortParam) ? sortParam : "created_at";

  const apply = useCallback(
    (nextFilters: TraceFilters, nextSort: TraceSort) => {
      const params = filtersToParams(nextFilters, nextSort);
      // Filter changes reset the page but keep the chosen page size.
      const size = searchParams.get("size");
      if (size) params.set("size", size);
      const next = params.size > 0 ? `${pathname}?${params}` : pathname;
      const current = searchParams.size > 0 ? `${pathname}?${searchParams}` : pathname;
      if (next !== current) router.replace(next);
    },
    [pathname, router, searchParams],
  );

  const setFilters = useCallback(
    (next: TraceFilters) => apply(next, sort),
    [apply, sort],
  );

  const setSort = useCallback(
    (next: TraceSort) => apply(filters, next),
    [apply, filters],
  );

  useEffect(() => {
    let cancelled = false;
    listTraces(scope, sort, filters, pageSize, (page - 1) * pageSize)
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
  }, [scope, sort, filters, page, pageSize, reloadKey]);

  // Explicit refetch for mutations that change rows server-side (bulk
  // visibility) without touching the URL state.
  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  // Live invalidation: new traces landing (CLI sync) and analysis verdicts
  // (outcome badge joins from trace_analysis) re-run the current query.
  useRealtimeRefetch("traces", reload);
  useRealtimeRefetch("trace_analysis", reload);

  // Out-of-range page (URL-edited or the list shrank): snap to the last page
  // instead of rendering a false empty state.
  useEffect(() => {
    if (result && result.traces.length === 0 && page > 1 && result.total > 0) {
      setPage(Math.max(1, Math.ceil(result.total / pageSize)));
    }
  }, [result, page, pageSize, setPage]);

  return {
    result,
    error,
    filters,
    setFilters,
    sort,
    setSort,
    page,
    setPage,
    pageSize,
    setPageSize,
    reload,
  };
}
