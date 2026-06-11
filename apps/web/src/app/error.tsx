"use client";

import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

// A redeploy invalidates the running tab's chunk URLs; client navigation then
// fails with one of these. One hard reload picks up the new build instead of
// stranding the user on an error page.
const STALE_BUNDLE =
  /ChunkLoadError|Loading chunk|dynamically imported module|Importing a module script|Failed to fetch/i;

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (!STALE_BUNDLE.test(`${error.name} ${error.message}`)) return;
    // sessionStorage guard: reload at most once per 10s so a genuinely
    // broken deploy degrades to the visible error page, not a reload loop.
    const last = Number(sessionStorage.getItem("stale-bundle-reload") ?? 0);
    if (Date.now() - last > 10_000) {
      sessionStorage.setItem("stale-bundle-reload", String(Date.now()));
      window.location.reload();
    }
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-medium">Something went wrong loading this page.</p>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        If the app was just updated, a reload picks up the new version.
      </p>
      <div className="mt-4 flex gap-2">
        <Button size="sm" onClick={() => window.location.reload()}>
          <RefreshCw data-slot="icon" /> Reload
        </Button>
        <Button size="sm" variant="outline" onClick={reset}>
          Try again
        </Button>
      </div>
    </div>
  );
}
