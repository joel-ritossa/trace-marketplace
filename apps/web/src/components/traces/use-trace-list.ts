"use client";

import { useEffect, useState } from "react";
import {
  listTraces,
  type TraceFilters,
  type TraceList,
  type TraceScope,
  type TraceSort,
} from "@/lib/api/traces";

/** Shared list-page state: scope + filters + sort → result, reloading on change. */
export function useTraceList(scope: TraceScope) {
  const [result, setResult] = useState<TraceList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<TraceFilters>({});
  const [sort, setSort] = useState<TraceSort>("created_at");

  useEffect(() => {
    let cancelled = false;
    listTraces(scope, sort, filters)
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
  }, [scope, sort, filters]);

  return { result, error, filters, setFilters, sort, setSort };
}
