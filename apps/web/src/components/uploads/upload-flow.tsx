"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FileStatusRow } from "@/components/uploads/flow-status";
import { UploadDropzone } from "@/components/uploads/upload-dropzone";
import { ApiError } from "@/lib/api/client";
import {
  createUpload,
  getUpload,
  UPLOAD_MAX_BYTES,
  UPLOAD_MAX_MB,
  type Upload,
} from "@/lib/api/uploads";
import { publicEnv } from "@/lib/env";

const POLL_MS = 1000;

export type FileFlow =
  | { id: number; filename: string; phase: "queued" }
  | { id: number; filename: string; phase: "uploading" }
  | { id: number; filename: string; phase: "rejected"; message: string }
  | { id: number; filename: string; phase: "tracking"; upload: Upload }
  | { id: number; filename: string; phase: "done"; upload: Upload };

/** Multi-file dropzone flow (4_pages.md /uploads): each file is its own
 *  upload record, sent sequentially to stay inside the per-user upload rate
 *  limit; one poll loop tracks every in-flight ingestion. */
export function UploadFlow({ onChanged }: { onChanged?: () => void }) {
  const [flows, setFlows] = useState<FileFlow[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const nextId = useRef(0);
  const onChangedRef = useRef(onChanged);
  useEffect(() => {
    onChangedRef.current = onChanged;
  }, [onChanged]);

  const patch = useCallback((id: number, next: Partial<FileFlow>) => {
    setFlows((prev) => prev.map((f) => (f.id === id ? ({ ...f, ...next } as FileFlow) : f)));
  }, []);

  const busy = flows.some((f) => f.phase === "queued" || f.phase === "uploading");

  async function onFiles(files: File[]) {
    const max = publicEnv.uploadMaxFiles;
    setNotice(
      files.length > max
        ? `Only the first ${max} files were accepted — the batch limit is ${max}.`
        : null,
    );

    const batch = files.slice(0, max).map((file) => {
      const id = nextId.current++;
      const flow: FileFlow =
        file.size > UPLOAD_MAX_BYTES
          ? {
              id,
              filename: file.name,
              phase: "rejected",
              message: `File exceeds the ${UPLOAD_MAX_MB} MB limit.`,
            }
          : { id, filename: file.name, phase: "queued" };
      return { file, flow };
    });
    setFlows(batch.map((b) => b.flow));

    for (const { file, flow } of batch) {
      if (flow.phase === "rejected") continue;
      patch(flow.id, { phase: "uploading" });
      try {
        const created = await createUpload(file);
        const upload = await getUpload(created.upload_id);
        const terminal = upload.status === "complete" || upload.status === "failed";
        patch(flow.id, { phase: terminal ? "done" : "tracking", upload });
        onChangedRef.current?.();
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Upload failed. Check the API is running.";
        patch(flow.id, { phase: "rejected", message });
      }
    }
  }

  // One poll loop over every in-flight ingestion; keyed on the id set so it
  // survives per-tick state updates and stops itself when nothing is tracking.
  const flowsRef = useRef(flows);
  useEffect(() => {
    flowsRef.current = flows;
  }, [flows]);
  const trackingKey = flows
    .filter((f) => f.phase === "tracking")
    .map((f) => f.id)
    .join(",");
  useEffect(() => {
    if (trackingKey === "") return;
    const timer = setInterval(() => {
      for (const flow of flowsRef.current) {
        if (flow.phase !== "tracking") continue;
        getUpload(flow.upload.upload_id)
          .then((upload) => {
            const terminal = upload.status === "complete" || upload.status === "failed";
            patch(flow.id, { phase: terminal ? "done" : "tracking", upload });
            if (terminal) onChangedRef.current?.();
          })
          .catch(() => {}); // transient poll failure; keep polling
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [trackingKey, patch]);

  return (
    <div>
      <UploadDropzone disabled={busy} onFiles={onFiles} />
      {notice && <p className="mt-3 text-sm text-warning-deep">{notice}</p>}
      {flows.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5">
          {flows.map((flow) => (
            <FileStatusRow key={flow.id} flow={flow} />
          ))}
        </ul>
      )}
    </div>
  );
}
