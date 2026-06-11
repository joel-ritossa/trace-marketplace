"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { BellPlus } from "lucide-react";
import { BusyLabel } from "@/components/traces/bulk-bar";
import { FilterChips } from "@/components/traces/filter-chips";
import { hasActiveFilters } from "@/components/traces/trace-filters";
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
import type { TraceFilters } from "@/lib/api/traces";

/** "Save as subscription" over the live filter state, with the current
 *  match total as the backfill preview (4_pages.md). Marketplace only —
 *  subscriptions match listed traces by construction. */
export function SaveSubscription({
  filters,
  total,
}: {
  filters: TraceFilters;
  total: number | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A subscribe-to-everything subscription is a footgun with no use.
  if (!hasActiveFilters(filters)) return null;

  async function onSave() {
    setBusy(true);
    setError(null);
    try {
      const sub = await createSubscription(name.trim(), cleanQuery(filters));
      router.push(`/subscriptions/${sub.subscription_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something failed — try again.");
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <BellPlus data-slot="icon" /> Save as subscription
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save this search as a subscription</DialogTitle>
            <DialogDescription>
              You’ll get a notification when a newly listed trace matches. Nothing is ever
              acquired automatically.
            </DialogDescription>
          </DialogHeader>
          <FilterChips filters={filters} />
          <p className="text-sm text-muted-foreground">
            {total === null ? "…" : `${total} listed trace${total === 1 ? "" : "s"} match today`}{" "}
            — the feed starts from this backfill.
          </p>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Subscription name"
            maxLength={120}
            autoFocus
          />
          {error && <p className="text-sm text-error-deep">{error}</p>}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={busy || name.trim() === ""} onClick={onSave}>
              <BusyLabel busy={busy}>Save subscription</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
