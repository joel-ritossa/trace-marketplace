"use client";

import { useCallback, useEffect, useState } from "react";
import { FlowStatus } from "@/components/uploads/flow-status";
import { UploadDropzone } from "@/components/uploads/upload-dropzone";
import { UploadsTable } from "@/components/uploads/uploads-table";
import { ApiError } from "@/lib/api/client";
import {
  createUpload,
  getUpload,
  listUploads,
  UPLOAD_MAX_BYTES,
  UPLOAD_MAX_MB,
  type Upload,
  type UploadListItem,
} from "@/lib/api/uploads";

const POLL_MS = 1000;

export type Flow =
  | { phase: "idle" }
  | { phase: "uploading"; filename: string }
  | { phase: "tracking"; upload: Upload }
  | { phase: "done"; upload: Upload }
  | { phase: "rejected"; message: string };

export function UploadFlow() {
  const [flow, setFlow] = useState<Flow>({ phase: "idle" });
  const [uploads, setUploads] = useState<UploadListItem[] | null>(null);

  const refreshList = useCallback(() => {
    listUploads()
      .then(({ uploads }) => setUploads(uploads))
      // Transient failure: keep what we have; only show empty if nothing loaded yet.
      .catch(() => setUploads((prev) => prev ?? []));
  }, []);

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  // Poll the active upload until it reaches a terminal status, keeping the
  // list in sync so its row's badge moves too. Keyed on the upload id so the
  // interval survives per-tick state updates.
  const trackingId = flow.phase === "tracking" ? flow.upload.upload_id : null;
  useEffect(() => {
    if (!trackingId) return;
    const timer = setInterval(async () => {
      try {
        const upload = await getUpload(trackingId);
        if (upload.status === "complete" || upload.status === "failed") {
          setFlow({ phase: "done", upload });
          refreshList();
        } else {
          setFlow({ phase: "tracking", upload });
        }
      } catch {
        // transient poll failure; keep polling
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [trackingId, refreshList]);

  async function onFile(file: File) {
    if (file.size > UPLOAD_MAX_BYTES) {
      setFlow({ phase: "rejected", message: `File exceeds the ${UPLOAD_MAX_MB} MB limit.` });
      return;
    }
    setFlow({ phase: "uploading", filename: file.name });
    try {
      const created = await createUpload(file);
      const upload = await getUpload(created.upload_id);
      setFlow(
        upload.status === "complete" || upload.status === "failed"
          ? { phase: "done", upload }
          : { phase: "tracking", upload },
      );
      refreshList();
    } catch (err) {
      let message = "Upload failed. Check the API is running.";
      if (err instanceof ApiError) {
        // The duplicate's row is already in the uploads list below.
        message =
          err.code === "duplicate_upload" ? `${err.message} It's in the list below.` : err.message;
      }
      setFlow({ phase: "rejected", message });
      refreshList();
    }
  }

  const busy = flow.phase === "uploading" || flow.phase === "tracking";

  return (
    <div className="flex flex-col gap-8">
      <div>
        <UploadDropzone disabled={busy} onFile={onFile} />
        <FlowStatus flow={flow} />
      </div>

      <section>
        <h2 className="text-sm font-semibold">Your uploads</h2>
        {uploads === null ? (
          <p className="mt-3 text-sm text-muted-foreground">Loading…</p>
        ) : uploads.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Nothing uploaded yet — your files will appear here.
          </p>
        ) : (
          <div className="mt-3">
            <UploadsTable uploads={uploads} />
          </div>
        )}
      </section>
    </div>
  );
}
