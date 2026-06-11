"use client";

import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import type { TraceFilters, TraceSort } from "@/lib/api/traces";

const SORT_OPTIONS: { value: TraceSort; label: string }[] = [
  { value: "created_at", label: "Newest" },
  { value: "duration_ms", label: "Longest" },
  { value: "span_count", label: "Most spans" },
];

const inputClass =
  "h-8 rounded-md border bg-background px-2 text-xs text-foreground placeholder:text-muted-foreground";

/** Search + filter bar shared by /traces and /marketplace. Debounces text
 *  input so each keystroke doesn't become an API call. */
export function TraceFiltersBar({
  onChange,
  sort,
  onSortChange,
}: {
  onChange: (filters: TraceFilters) => void;
  sort: TraceSort;
  onSortChange: (sort: TraceSort) => void;
}) {
  const [q, setQ] = useState("");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [hasErrors, setHasErrors] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const handle = setTimeout(() => {
      onChangeRef.current({
        q: q.trim() || undefined,
        provider: provider.trim() || undefined,
        model: model.trim() || undefined,
        has_errors: hasErrors || undefined,
        from: from ? `${from}T00:00:00Z` : undefined,
        to: to ? `${to}T23:59:59Z` : undefined,
      });
    }, 300);
    return () => clearTimeout(handle);
  }, [q, provider, model, hasErrors, from, to]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search traces…"
          className="h-8 w-56 pl-8 text-xs"
        />
      </div>
      <input
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        placeholder="Provider"
        className={`${inputClass} w-24`}
      />
      <input
        value={model}
        onChange={(e) => setModel(e.target.value)}
        placeholder="Model"
        className={`${inputClass} w-28`}
      />
      <input
        type="date"
        value={from}
        onChange={(e) => setFrom(e.target.value)}
        title="Started on or after"
        className={`${inputClass} w-32`}
      />
      <input
        type="date"
        value={to}
        onChange={(e) => setTo(e.target.value)}
        title="Started on or before"
        className={`${inputClass} w-32`}
      />
      <label className="flex h-8 cursor-pointer items-center gap-1.5 rounded-md border bg-background px-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={hasErrors}
          onChange={(e) => setHasErrors(e.target.checked)}
          className="size-3 accent-foreground"
        />
        Has errors
      </label>
      <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
        Sort
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as TraceSort)}
          className={inputClass}
        >
          {SORT_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/** True when any filter is active — drives the no-results-for-query state. */
export function hasActiveFilters(filters: TraceFilters): boolean {
  return Object.values(filters).some((v) => v !== undefined);
}
