import { BookMarked, Globe, Lock } from "lucide-react";
import type { TraceVisibility } from "@/lib/api/traces";
import { cn } from "@/lib/utils";

/** Visibility is always visible (4_pages.md): every trace rendering carries one. */
export function VisibilityBadge({ visibility }: { visibility: TraceVisibility }) {
  const listed = visibility === "listed";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        listed ? "bg-link-soft text-link-deep" : "bg-secondary text-muted-foreground",
      )}
    >
      {listed ? <Globe className="size-3" /> : <Lock className="size-3" />}
      {visibility}
    </span>
  );
}

export function LibraryBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-status-ok-soft px-2 py-0.5 text-xs font-medium text-status-ok">
      <BookMarked className="size-3" />
      in your library
    </span>
  );
}
