"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, ShoppingBag, Trash2 } from "lucide-react";
import { LibraryBadge } from "@/components/traces/badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import {
  acquireTrace,
  deleteTrace,
  updateTrace,
  type TraceDetail,
} from "@/lib/api/traces";

function errorMessage(err: unknown): string {
  // UI rule (4_pages.md): show the API's real reason, never a generic shrug.
  return err instanceof ApiError ? err.message : "Something failed — try again.";
}

function OwnerActions({
  trace,
  onChange,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
}) {
  const router = useRouter();
  const [tags, setTags] = useState(trace.tags.join(", "));
  const [description, setDescription] = useState(trace.description ?? "");
  const [confirmShare, setConfirmShare] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedTags = tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const dirty =
    parsedTags.join("\u0000") !== trace.tags.join("\u0000") ||
    description !== (trace.description ?? "");

  async function run(action: () => Promise<TraceDetail | void>) {
    setBusy(true);
    setError(null);
    try {
      const updated = await action();
      if (updated) onChange(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const saveMeta = () =>
    run(() =>
      updateTrace(trace.trace_id, {
        tags: parsedTags,
        description: description.trim() || null,
      }),
    );

  const setVisibility = (visibility: "private" | "listed") =>
    run(() =>
      updateTrace(trace.trace_id, { visibility, confirm_ownership: confirmShare }),
    );

  const onDelete = () =>
    run(async () => {
      await deleteTrace(trace.trace_id);
      router.push("/traces");
    });

  return (
    <section className="rounded-lg border bg-background px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 grow flex-col gap-2">
          <label className="text-xs text-muted-foreground" htmlFor="trace-tags">
            Tags (comma-separated) and description — shown on the marketplace listing
          </label>
          <Input
            id="trace-tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="e.g. customer-support, tool-use, failure"
            className="h-8 text-xs"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this trace? What makes it worth acquiring?"
            rows={2}
            className="rounded-md border bg-background px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground"
          />
          {dirty && (
            <div>
              <Button size="sm" variant="outline" disabled={busy} onClick={saveMeta}>
                {busy && <Loader2 className="animate-spin" />} Save changes
              </Button>
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          {trace.visibility === "private" ? (
            <>
              <label className="flex max-w-64 cursor-pointer items-start gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={confirmShare}
                  onChange={(e) => setConfirmShare(e.target.checked)}
                  className="mt-0.5 size-3 accent-foreground"
                />
                This trace data is mine to share and may be inspected by any
                signed-in user.
              </label>
              <Button
                size="sm"
                disabled={busy || !confirmShare}
                onClick={() => setVisibility("listed")}
              >
                {busy && <Loader2 className="animate-spin" />} List on marketplace
              </Button>
            </>
          ) : (
            <>
              <p className="max-w-64 text-right text-xs text-muted-foreground">
                Listed on the marketplace: any signed-in user can inspect and
                acquire it. Unlisting revokes consumer access.
              </p>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => setVisibility("private")}
              >
                {busy && <Loader2 className="animate-spin" />} Unlist
              </Button>
            </>
          )}

          {confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-error-deep">
                Permanently delete this trace and its spans?
              </span>
              <Button size="sm" variant="destructive" disabled={busy} onClick={onDelete}>
                Delete
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => setConfirmDelete(false)}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              className="text-error-deep hover:text-error-deep"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 /> Delete trace
            </Button>
          )}
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-error-deep">{error}</p>}
    </section>
  );
}

function ConsumerActions({
  trace,
  onChange,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (trace.acquired) {
    return (
      <section className="flex items-center gap-3 rounded-lg border bg-background px-4 py-3">
        <LibraryBadge />
        <p className="text-xs text-muted-foreground">
          You acquired this trace — download the raw payload anytime from here or
          your library.
        </p>
      </section>
    );
  }

  async function onAcquire() {
    setBusy(true);
    setError(null);
    try {
      await acquireTrace(trace.trace_id);
      onChange({ ...trace, acquired: true, can_download: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background px-4 py-3">
      <p className="text-xs text-muted-foreground">
        Inspection is free for listed traces. Acquire it ($0) to download the raw
        payload and keep it in your library.
      </p>
      <div className="flex flex-col items-end gap-1">
        <Button size="sm" disabled={busy} onClick={onAcquire}>
          {busy ? <Loader2 className="animate-spin" /> : <ShoppingBag />} Acquire — free
        </Button>
        {error && <p className="text-xs text-error-deep">{error}</p>}
      </div>
    </section>
  );
}

/** Detail-page actions, driven by the API's relationship flags (4_pages.md). */
export function TraceActions({
  trace,
  onChange,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
}) {
  return trace.is_owner ? (
    <OwnerActions trace={trace} onChange={onChange} />
  ) : (
    <ConsumerActions trace={trace} onChange={onChange} />
  );
}
