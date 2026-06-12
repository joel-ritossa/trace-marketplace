"use client";

import { BusyLabel } from "@/components/traces/bulk-bar";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import {
    bulkAcquire,
    bulkDownload,
    bulkVisibility,
    type BulkAcquireResult,
} from "@/lib/api/traces";
import { Download, ShoppingBag } from "lucide-react";
import { useState } from "react";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something failed — try again.";
}

function tally(counts: Map<string, number>, labels: Record<string, string>): string {
  return [...counts.entries()]
    .map(([status, n]) => `${n} ${labels[status] ?? status}`)
    .join(" · ");
}

function count(results: { status: string }[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const { status } of results) counts.set(status, (counts.get(status) ?? 0) + 1);
  return counts;
}

const ACQUIRE_LABELS: Record<string, string> = {
  acquired: "acquired",
  already_acquired: "already in library",
  not_listed: "no longer listed",
  not_found: "not found",
};

/** Feed/marketplace bulk acquire: confirm states the final count; the
 *  result is itemized and offers the labeled download (4_pages.md). */
export function BulkAcquireAction({
  ids,
  onDone,
}: {
  ids: string[];
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BulkAcquireResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onAcquire() {
    setBusy(true);
    setError(null);
    try {
      setResult(await bulkAcquire(ids));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const acquiredIds =
    result?.filter((r) => r.status === "acquired" || r.status === "already_acquired") ?? [];

  function close(open: boolean) {
    setOpen(open);
    if (!open && result !== null) {
      setResult(null);
      onDone();
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <ShoppingBag data-slot="icon" /> Acquire {ids.length}
      </Button>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent>
          {result === null ? (
            <>
              <DialogHeader>
                <DialogTitle>Acquire {ids.length} traces?</DialogTitle>
                <DialogDescription>
                  Acquisition is free and idempotent; acquired traces land saved,
                  ready to download.
                </DialogDescription>
              </DialogHeader>
              {error && <p className="text-sm text-error-deep">{error}</p>}
              <DialogFooter>
                <Button variant="outline" size="sm" onClick={() => close(false)}>
                  Cancel
                </Button>
                <Button size="sm" disabled={busy} onClick={onAcquire}>
                  <BusyLabel busy={busy}>Acquire {ids.length}</BusyLabel>
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Acquisition result</DialogTitle>
                <DialogDescription>{tally(count(result), ACQUIRE_LABELS)}</DialogDescription>
              </DialogHeader>
              {error && <p className="text-sm text-error-deep">{error}</p>}
              <DialogFooter>
                {acquiredIds.length > 0 && (
                  <BulkDownloadAction
                    ids={acquiredIds.map((r) => r.trace_id)}
                    label={`Download ${acquiredIds.length} now`}
                    onError={setError}
                  />
                )}
                <Button variant="outline" size="sm" onClick={() => close(false)}>
                  Done
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** My-Traces bulk list/unlist with batched consent: one dialog naming the
 *  exact count, the same affirmative ownership checkbox, once for the batch
 *  (4_pages.md). */
export function BulkVisibilityActions({
  ids,
  onDone,
}: {
  ids: string[];
  onDone: (summary: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [confirmShare, setConfirmShare] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(visibility: "listed" | "private") {
    setBusy(true);
    setError(null);
    try {
      const results = await bulkVisibility(ids, visibility, visibility === "listed");
      const updated = results.filter((r) => r.status === "updated").length;
      const missing = results.length - updated;
      setConfirming(false);
      setConfirmShare(false);
      onDone(
        `${updated} ${visibility === "listed" ? "listed" : "unlisted"}` +
          (missing > 0 ? ` · ${missing} not found` : ""),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setConfirming(true)}>
        List {ids.length}
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => run("private")}>
        <BusyLabel busy={busy && !confirming}>Unlist {ids.length}</BusyLabel>
      </Button>
      {error && !confirming && <p className="text-xs text-error-deep">{error}</p>}
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>List {ids.length} traces on the marketplace?</DialogTitle>
            <DialogDescription>
              Listing makes these {ids.length} traces inspectable and acquirable by any
              signed-in user. Unlisting later revokes consumer access.
            </DialogDescription>
          </DialogHeader>
          <label className="flex cursor-pointer items-start gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={confirmShare}
              onChange={(e) => setConfirmShare(e.target.checked)}
              className="mt-0.5 size-3.5 accent-foreground"
            />
            This trace data is mine to share and may be inspected by any signed-in user.
          </label>
          {error && <p className="text-sm text-error-deep">{error}</p>}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={busy || !confirmShare} onClick={() => run("listed")}>
              <BusyLabel busy={busy}>List {ids.length} traces</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Library bulk download: zip of payloads + labels.jsonl. Owners' own
 *  traces come back raw, acquired ones scrubbed (7_redaction.md). */
export function BulkDownloadAction({
  ids,
  label,
  onError,
}: {
  ids: string[];
  label?: string;
  onError?: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function onDownload() {
    setBusy(true);
    try {
      await bulkDownload(ids);
    } catch (err) {
      onError?.(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button size="sm" disabled={busy} onClick={onDownload}>
      <BusyLabel busy={busy}>
        <Download data-slot="icon" /> {label ?? `Download ${ids.length}`}
      </BusyLabel>
    </Button>
  );
}
