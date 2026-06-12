"use client";

import { LibraryBadge } from "@/components/traces/badges";
import { BusyLabel } from "@/components/traces/bulk-bar";
import { SimilarBehaviorButton } from "@/components/traces/similar-traces";
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
import {
    acquireTrace,
    deleteTrace,
    downloadTrace,
    updateTrace,
    type TraceDetail,
} from "@/lib/api/traces";
import { Download, Loader2, ShoppingBag, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

function errorMessage(err: unknown): string {
  // UI rule (4_pages.md): show the API's real reason, never a generic shrug.
  return err instanceof ApiError ? err.message : "Something failed — try again.";
}

/** The header-strip actions cluster (4_pages.md trace-detail layout): one
 *  place for download, acquire, and the owner's manage actions, driven by
 *  the API's relationship flags. */
export function TraceHeaderActions({
  trace,
  onChange,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
}) {
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {trace.acquired ? (
          <LibraryBadge />
        ) : (
          trace.visibility === "listed" && (
            <AcquireButton trace={trace} onChange={onChange} onError={setError} />
          )
        )}
        <SimilarBehaviorButton trace={trace} />
        <DownloadButton trace={trace} onError={setError} />
        {trace.is_owner && <VisibilityButton trace={trace} onChange={onChange} onError={setError} />}
        {trace.is_owner && <DeleteButton trace={trace} onError={setError} />}
      </div>
      {error && <p className="text-xs text-error-deep">{error}</p>}
      {!trace.can_download && (
        <p className="text-xs text-muted-foreground">
          Inspection is free; acquire ($0) to download the payload.
        </p>
      )}
    </div>
  );
}

function AcquireButton({
  trace,
  onChange,
  onError,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
  onError: (message: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function onAcquire() {
    setBusy(true);
    onError(null);
    try {
      await acquireTrace(trace.trace_id);
      onChange({ ...trace, acquired: true, can_download: true });
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button size="sm" disabled={busy} onClick={onAcquire} title="Free — lands saved">
      {busy ? <Loader2 className="animate-spin" /> : <ShoppingBag />} Acquire — free
    </Button>
  );
}

function DownloadButton({
  trace,
  onError,
}: {
  trace: TraceDetail;
  onError: (message: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function onDownload() {
    setBusy(true);
    onError(null);
    try {
      await downloadTrace(trace.trace_id, `${trace.name.replaceAll("/", "_")}.json`);
    } catch {
      onError("Download failed — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button
      size="sm"
      variant="outline"
      disabled={!trace.can_download || busy}
      onClick={onDownload}
      title={trace.can_download ? undefined : "Acquire this trace to download it"}
    >
      <Download /> Download raw
    </Button>
  );
}

function VisibilityButton({
  trace,
  onChange,
  onError,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
  onError: (message: string | null) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [confirmShare, setConfirmShare] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  async function setVisibility(visibility: "private" | "listed") {
    setBusy(true);
    onError(null);
    setDialogError(null);
    try {
      const updated = await updateTrace(trace.trace_id, {
        visibility,
        confirm_ownership: visibility === "listed" ? confirmShare : undefined,
      });
      setConfirming(false);
      setConfirmShare(false);
      onChange(updated);
    } catch (err) {
      if (visibility === "listed") setDialogError(errorMessage(err));
      else onError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (trace.visibility === "listed") {
    return (
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => setVisibility("private")}
        title="Unlisting revokes consumer access"
      >
        <BusyLabel busy={busy}>Unlist</BusyLabel>
      </Button>
    );
  }

  return (
    <>
      <Button size="sm" onClick={() => setConfirming(true)}>
        List on marketplace
      </Button>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>List this trace on the marketplace?</DialogTitle>
            <DialogDescription>
              Listing makes it inspectable and acquirable by any signed-in user. Unlisting
              later revokes consumer access.
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
          {dialogError && <p className="text-sm text-error-deep">{dialogError}</p>}
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button size="sm" disabled={busy || !confirmShare} onClick={() => setVisibility("listed")}>
              <BusyLabel busy={busy}>List trace</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DeleteButton({
  trace,
  onError,
}: {
  trace: TraceDetail;
  onError: (message: string | null) => void;
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onDelete() {
    setBusy(true);
    onError(null);
    try {
      await deleteTrace(trace.trace_id);
      router.push("/traces");
    } catch (err) {
      setConfirming(false);
      onError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        aria-label="Delete trace"
        className="text-error-deep hover:text-error-deep"
        onClick={() => setConfirming(true)}
      >
        <Trash2 />
      </Button>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this trace?</DialogTitle>
            <DialogDescription>
              Permanently deletes the trace and its spans. Consumers lose access; the raw
              upload stays in your history.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button size="sm" variant="destructive" disabled={busy} onClick={onDelete}>
              <BusyLabel busy={busy}>Delete trace</BusyLabel>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Owner-only tags/description editing — lives in the overview region; the
 *  consumer-facing rendering happens on the marketplace listing. */
export function TraceMetaEditor({
  trace,
  onChange,
}: {
  trace: TraceDetail;
  onChange: (trace: TraceDetail) => void;
}) {
  const [tags, setTags] = useState(trace.tags.join(", "));
  const [description, setDescription] = useState(trace.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedTags = tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const dirty =
    parsedTags.join("\u0000") !== trace.tags.join("\u0000") ||
    description !== (trace.description ?? "");

  async function saveMeta() {
    setBusy(true);
    setError(null);
    try {
      onChange(
        await updateTrace(trace.trace_id, {
          tags: parsedTags,
          description: description.trim() || null,
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-background px-4 py-3">
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
            <BusyLabel busy={busy}>Save changes</BusyLabel>
          </Button>
        </div>
      )}
      {error && <p className="text-xs text-error-deep">{error}</p>}
    </div>
  );
}
