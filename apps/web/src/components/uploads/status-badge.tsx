import { Loader2 } from "lucide-react";
import type { UploadStatus } from "@/lib/api/uploads";
import { cn } from "@/lib/utils";

// DESIGN.md status palette: soft backgrounds, deep text, spinner on processing.
const styles: Record<UploadStatus, string> = {
  received: "bg-secondary text-muted-foreground",
  processing: "bg-secondary text-muted-foreground",
  complete: "bg-status-ok-soft text-status-ok",
  failed: "bg-error-soft text-error-deep",
};

export function StatusBadge({ status }: { status: UploadStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        styles[status],
      )}
    >
      {status === "processing" && <Loader2 className="size-3 animate-spin" />}
      {status}
    </span>
  );
}
