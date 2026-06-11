"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TracesTable } from "@/components/traces/traces-table";
import { listTraces, type TraceListItem, type TraceSort } from "@/lib/api/traces";

const SORT_OPTIONS: { value: TraceSort; label: string }[] = [
  { value: "created_at", label: "Newest" },
  { value: "duration_ms", label: "Longest" },
  { value: "span_count", label: "Most spans" },
];

export default function TracesPage() {
  const [traces, setTraces] = useState<TraceListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<TraceSort>("created_at");

  useEffect(() => {
    let cancelled = false;
    listTraces(sort)
      .then(({ traces }) => {
        if (!cancelled) {
          setTraces(traces);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Could not load traces. Check the API is running.");
      });
    return () => {
      cancelled = true;
    };
  }, [sort]);

  return (
    <div>
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Traces</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Traces parsed from your uploads.
          </p>
        </div>
        {traces !== null && traces.length > 0 && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Sort
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as TraceSort)}
              className="rounded-md border bg-background px-2 py-1.5 text-xs text-foreground"
            >
              {SORT_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="mt-8">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : traces === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : traces.length === 0 ? (
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
          <TracesTable traces={traces} />
        )}
      </div>
    </div>
  );
}
