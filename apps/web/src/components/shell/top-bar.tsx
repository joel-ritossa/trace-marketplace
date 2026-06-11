"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ChevronRight } from "lucide-react";
import { AccountMenu } from "@/components/shell/account-menu";
import { NotificationBell } from "@/components/shell/notification-bell";

const SECTIONS: Record<string, string> = {
  traces: "Traces",
  uploads: "Uploads",
  review: "Review",
  marketplace: "Browse",
  subscriptions: "Subscriptions",
  library: "Library",
  notifications: "Notifications",
  settings: "Settings",
};

/** Where a detail page's parent crumb points when the arriving surface set
 *  `?from=` (4_pages.md: back navigation is contextual). */
const FROM_CRUMBS: Record<string, { href: string; label: string }> = {
  traces: { href: "/traces", label: "Traces" },
  marketplace: { href: "/marketplace", label: "Browse" },
  library: { href: "/library", label: "Library" },
  review: { href: "/review", label: "Review" },
  subscriptions: { href: "/subscriptions", label: "Subscriptions" },
  notifications: { href: "/notifications", label: "Notifications" },
};

function Crumbs() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [section, detail] = pathname.split("/").filter(Boolean);

  const sectionLabel = SECTIONS[section];
  if (!sectionLabel) return null;

  if (!detail) {
    // /uploads is the Traces surface's second tab, so it crumbs as a child.
    if (section === "uploads") {
      return (
        <span className="flex min-w-0 items-center gap-1.5">
          <Link href="/traces" className="truncate transition-colors hover:text-foreground">
            Traces
          </Link>
          <ChevronRight aria-hidden className="size-3.5 shrink-0" />
          <span className="font-medium text-foreground">Uploads</span>
        </span>
      );
    }
    return <span className="font-medium text-foreground">{sectionLabel}</span>;
  }

  const from = searchParams.get("from");
  const parent =
    (from ? FROM_CRUMBS[from] : undefined) ??
    (section === "traces" ? FROM_CRUMBS.traces : { href: `/${section}`, label: sectionLabel });
  const leaf =
    section === "review" ? "Resolve" : section === "subscriptions" ? "Feed" : "Trace";

  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Link href={parent.href} className="truncate transition-colors hover:text-foreground">
        {parent.label}
      </Link>
      <ChevronRight aria-hidden className="size-3.5 shrink-0" />
      <span className="font-medium text-foreground">{leaf}</span>
    </span>
  );
}

export function TopBar({ email }: { email: string }) {
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between gap-4 border-b bg-background px-6">
      <div className="min-w-0 text-sm text-muted-foreground">
        {/* useSearchParams needs a boundary; the crumb is cosmetic, so blank is a fine fallback. */}
        <Suspense fallback={null}>
          <Crumbs />
        </Suspense>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <NotificationBell />
        <AccountMenu email={email} />
      </div>
    </header>
  );
}
