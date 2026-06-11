"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { BellPlus, Search } from "lucide-react";
import { BusyLabel } from "@/components/traces/bulk-bar";
import { FilterChips } from "@/components/traces/filter-chips";
import {
  FilterFields,
  hasActiveFilters,
  mergeText,
  textFromFilters,
  type FilterText,
} from "@/components/traces/trace-filters";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { cleanQuery, createSubscription } from "@/lib/api/subscriptions";
import { listTraces, type TraceFilters } from "@/lib/api/traces";

/** Build a subscription in place: pick filters, preview the live match count
 *  against the marketplace, then save. The same query vocabulary as the
 *  Browse "Save as subscription" flow — one filter language, two entry
 *  points. */
export function NewSubscription() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [filters, setFilters] = useState<TraceFilters>({});
  const [text, setText] = useState<FilterText>(() => textFromFilters({}));
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const effective = cleanQuery(mergeText(filters, text));
  const active = hasActiveFilters(effective);

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      setFilters({});
      setText(textFromFilters({}));
      setName("");
      setPreview(null);
      setError(null);
    }
  }

  // Any edit invalidates the previewed count.
  function set(patch: Partial<TraceFilters>) {
    setFilters((prev) => ({ ...prev, ...patch }));
    setPreview(null);
  }
  function onText(next: FilterText) {
    setText(next);
    setPreview(null);
  }

  async function onSearch() {
    setSearching(true);
    setError(null);
    try {
      const res = await listTraces("marketplace", "created_at", effective, 1, 0);
      setPreview(res.total);
    } catch {
      setError("Could not run the search. Check the API is running.");
    } finally {
      setSearching(false);
    }
  }

  async function onCreate() {
    setSaving(true);
    setError(null);
    try {
      const sub = await createSubscription(name.trim(), effective);
      router.push(`/subscriptions/${sub.subscription_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something failed — try again.");
      setSaving(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => onOpenChange(true)}>
        <BellPlus data-slot="icon" /> New subscription
      </Button>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>New subscription</DialogTitle>
            <DialogDescription>
              Pick filters, preview what matches in the marketplace today, then save. You’ll be
              notified when a newly listed trace matches — nothing is ever acquired automatically.
            </DialogDescription>
          </DialogHeader>

          <Input
            value={text.q}
            onChange={(e) => onText({ ...text, q: e.target.value })}
            placeholder="Search text (optional)…"
            className="h-8 text-xs"
          />
          <FilterFields
            filters={filters}
            set={set}
            text={text}
            setText={onText}
            className="grid-cols-2 sm:grid-cols-3"
          />
          <FilterChips filters={effective} />

          <div className="flex items-center gap-3">
            <Button size="sm" variant="outline" disabled={!active || searching} onClick={onSearch}>
              <BusyLabel busy={searching}>
                <Search data-slot="icon" /> Search
              </BusyLabel>
            </Button>
            <p className="text-sm text-muted-foreground">
              {!active
                ? "A subscription needs at least one filter."
                : preview === null
                  ? "Preview the current match count."
                  : `${preview} listed trace${preview === 1 ? "" : "s"} match today — the feed starts from this backfill.`}
            </p>
          </div>

          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Subscription name"
            maxLength={120}
          />
          {error && <p className="text-sm text-error-deep">{error}</p>}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={saving || !active || name.trim() === ""} onClick={onCreate}>
              <BusyLabel busy={saving}>Create subscription</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
