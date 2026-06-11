"use client";

import { X } from "lucide-react";
import {
  filterChips,
  removeChip,
  type FilterChip,
} from "@/components/traces/filter-state";
import type { TraceFilters } from "@/lib/api/traces";
import { cn } from "@/lib/utils";

/** Active predicates rendered verbatim (`faithfulness ≥ 0.8 ×`) — the same
 *  artifact on search pages, subscription rows, and feed headers
 *  (4_pages.md). Read-only when onChange is omitted. */
export function FilterChips({
  filters,
  onChange,
  className,
}: {
  filters: TraceFilters;
  onChange?: (filters: TraceFilters) => void;
  className?: string;
}) {
  const chips = filterChips(filters);
  if (chips.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {chips.map((chip) => (
        <Chip
          key={`${chip.key}:${chip.value ?? ""}:${chip.label}`}
          chip={chip}
          onRemove={onChange ? () => onChange(removeChip(filters, chip)) : undefined}
        />
      ))}
    </div>
  );
}

function Chip({ chip, onRemove }: { chip: FilterChip; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border bg-secondary px-2 py-0.5 font-mono text-xs text-foreground">
      {chip.label}
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove filter ${chip.label}`}
          onClick={onRemove}
          className="-mr-0.5 rounded-full p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  );
}
