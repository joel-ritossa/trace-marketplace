import { apiDownload, apiFetch } from "@/lib/api/client";

// Types mirror services/api/app/schemas/upload.py — keep in sync.

export type UploadStatus = "received" | "processing" | "complete" | "failed";

export type UploadCreated = {
  upload_id: string;
  status: UploadStatus;
  sha256: string;
};

export type Upload = {
  upload_id: string;
  filename: string;
  status: UploadStatus;
  error_message: string | null;
  parse_warnings: Record<string, unknown> | null;
  trace_ids: string[];
  created_at: string;
  processed_at: string | null;
};

export type UploadListItem = {
  upload_id: string;
  filename: string;
  size_bytes: number;
  status: UploadStatus;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
};

export type UploadList = {
  uploads: UploadListItem[];
  total: number;
};

// Mirrors the API's UPLOAD_MAX_BYTES default — keep in sync if that changes.
// Client-side pre-check only; the server's 413 is authoritative.
export const UPLOAD_MAX_BYTES = 25 * 1024 * 1024;
export const UPLOAD_MAX_MB = UPLOAD_MAX_BYTES / (1024 * 1024);

export async function createUpload(file: File): Promise<UploadCreated> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<UploadCreated>("/v1/uploads", { method: "POST", body });
}

export async function getUpload(uploadId: string): Promise<Upload> {
  return apiFetch<Upload>(`/v1/uploads/${uploadId}`);
}

export async function listUploads(): Promise<UploadList> {
  return apiFetch<UploadList>("/v1/uploads");
}

export async function downloadUpload(uploadId: string, filename: string): Promise<void> {
  return apiDownload(`/v1/uploads/${uploadId}/download`, filename);
}
