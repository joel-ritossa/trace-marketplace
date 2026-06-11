"use client";

import { useCallback, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

// Mirrors the API's per-call cap.
export const BULK_MAX = 100;

/** Explicit-selection state for bulk actions (4_pages.md): operates only on
 *  visibly checked rows — page-level select-all exists, "select all
 *  matching" (unseen rows) does not. */
export function useSelection() {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < BULK_MAX) next.add(id);
      return next;
    });
  }, []);

  /** Check or uncheck a visible page of ids, respecting the cap. */
  const setAll = useCallback((ids: readonly string[], checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (!checked) next.delete(id);
        else if (next.size < BULK_MAX || next.has(id)) next.add(id);
      }
      return next;
    });
  }, []);

  const clear = useCallback(() => setSelected(new Set()), []);

  return { selected, toggle, setAll, clear };
}

export function SelectBox({
  checked,
  indeterminate,
  onToggle,
  label,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = !checked && (indeterminate ?? false);
      }}
      onChange={onToggle}
      onClick={(e) => e.stopPropagation()}
      aria-label={label}
      className="size-3.5 shrink-0 accent-foreground"
    />
  );
}

/** Persistent bulk bar: selection count, the page's actions, clear. Shown
 *  while anything is selected. */
export function BulkBar({
  count,
  onClear,
  children,
  status,
}: {
  count: number;
  onClear: () => void;
  children: React.ReactNode;
  status?: string | null;
}) {
  if (count === 0) return null;
  return (
    <div className="sticky bottom-4 z-10 mt-4 flex flex-wrap items-center gap-3 rounded-lg border bg-background px-4 py-2.5 shadow-md">
      <p className="text-sm font-medium tabular-nums">
        {count} selected{count >= BULK_MAX ? " (max)" : ""}
      </p>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
      {status && <p className="text-xs text-muted-foreground">{status}</p>}
      <Button variant="ghost" size="sm" className="ml-auto" onClick={onClear}>
        <X data-slot="icon" /> Clear
      </Button>
    </div>
  );
}

export function BusyLabel({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <>
      {busy && <Loader2 data-slot="icon" className="animate-spin" />}
      {children}
    </>
  );
}
