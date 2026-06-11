"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BellRing, Check, Pencil, Trash2, X } from "lucide-react";
import { FilterChips } from "@/components/traces/filter-chips";
import { NewSubscription } from "@/components/traces/new-subscription";
import { BehaviorAnchor } from "@/components/traces/similar-traces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import {
  deleteSubscription,
  listSubscriptions,
  updateSubscription,
  type Subscription,
} from "@/lib/api/subscriptions";
import { formatDate } from "@/lib/format";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something failed — try again.";
}

function Row({ sub, onChanged }: { sub: Subscription; onChanged: () => void }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(sub.name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const rename = () =>
    run(async () => {
      if (name.trim() && name.trim() !== sub.name) {
        await updateSubscription(sub.subscription_id, { name: name.trim() });
      }
      setRenaming(false);
    });

  return (
    <li className="rounded-lg border bg-background px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {renaming ? (
            <span className="flex items-center gap-1.5">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && rename()}
                maxLength={120}
                autoFocus
                className="h-7 w-56 text-sm"
              />
              <Button size="icon-sm" variant="ghost" aria-label="Save name" onClick={rename}>
                <Check />
              </Button>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Cancel rename"
                onClick={() => {
                  setRenaming(false);
                  setName(sub.name);
                }}
              >
                <X />
              </Button>
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              <Link
                href={`/subscriptions/${sub.subscription_id}`}
                className="truncate text-sm font-medium hover:underline"
              >
                {sub.name}
              </Link>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label={`Rename ${sub.name}`}
                disabled={busy}
                onClick={() => setRenaming(true)}
              >
                <Pencil />
              </Button>
            </span>
          )}
          <FilterChips filters={sub.query} className="mt-1.5" />
          <div className="mt-1.5 empty:hidden">
            <BehaviorAnchor sub={sub} />
          </div>
          <p className="mt-1.5 font-mono text-xs text-muted-foreground">
            {sub.match_count} matching now
            {sub.last_match_at ? ` · last match ${formatDate(sub.last_match_at)}` : " · no new matches yet"}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {confirmingDelete ? (
            <div className="flex flex-col items-end gap-1.5">
              <p className="max-w-72 text-right text-xs text-error-deep">
                Delete “{sub.name}”? Match notifications stop; your library is unaffected.
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busy}
                  onClick={() => run(() => deleteSubscription(sub.subscription_id))}
                >
                  Delete
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => setConfirmingDelete(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              className="text-error-deep hover:text-error-deep"
              onClick={() => setConfirmingDelete(true)}
            >
              <Trash2 data-slot="icon" /> Delete
            </Button>
          )}
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-error-deep">{error}</p>}
    </li>
  );
}

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    listSubscriptions()
      .then((res) => {
        setSubs(res);
        setError(null);
      })
      .catch(() => setError("Could not load subscriptions. Check the API is running."));
  }, []);

  useEffect(reload, [reload]);

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Subscriptions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Saved marketplace searches. You’re notified when a newly listed trace matches —
            nothing is ever acquired automatically.
          </p>
        </div>
        <NewSubscription />
      </div>

      <div className="mt-6">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : subs === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : subs.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <BellRing className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No subscriptions yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Filter the marketplace, then “Save as subscription” to follow new matches.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href="/marketplace">Search the marketplace</Link>
            </Button>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {subs.map((sub) => (
              <Row key={sub.subscription_id} sub={sub} onChanged={reload} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
