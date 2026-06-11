"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BellRing,
  BookMarked,
  ClipboardCheck,
  ScrollText,
  Settings,
  Store,
  type LucideIcon,
} from "lucide-react";
import { BrandMark } from "@/components/shell/brand-mark";
import { listReviewItems } from "@/lib/api/review";
import { cn } from "@/lib/utils";

type Item = { href: string; label: string; icon: LucideIcon; alsoMatches?: string };

/** The supply/demand IA (4_pages.md nav): Workspace is your data moving
 *  through the pipeline; Marketplace is everyone's listed data moving toward
 *  your library. */
const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "Workspace",
    items: [
      // /uploads is the Traces surface's second tab, not its own nav slot.
      { href: "/traces", label: "Traces", icon: ScrollText, alsoMatches: "/uploads" },
      { href: "/review", label: "Review", icon: ClipboardCheck },
    ],
  },
  {
    label: "Marketplace",
    items: [
      { href: "/marketplace", label: "Browse", icon: Store },
      { href: "/subscriptions", label: "Subscriptions", icon: BellRing },
      { href: "/library", label: "Library", icon: BookMarked },
    ],
  },
];

function NavItem({ item, active, badge }: { item: Item; active: boolean; badge?: number }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={item.label}
      className={cn(
        "relative flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
        active
          ? "bg-secondary font-medium text-foreground"
          : "text-muted-foreground hover:bg-canvas-soft hover:text-foreground",
      )}
    >
      {/* ex-app-shell-row active indicator */}
      {active && <span aria-hidden className="absolute -left-2 h-4 w-0.5 rounded-full bg-primary" />}
      <Icon className="size-4 shrink-0" strokeWidth={1.75} />
      <span className="hidden min-w-0 flex-1 truncate md:inline">{item.label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="hidden rounded-full bg-secondary px-1.5 font-mono text-[10px] leading-4 text-muted-foreground md:inline">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </Link>
  );
}

/** Open review items, fetched per navigation — advisory, allowed to lag.
 *  A dead API renders no badge, never broken UI. */
function useOpenReviewCount(pathname: string) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    listReviewItems({ status: "open", limit: 1 })
      .then((res) => {
        if (!cancelled) setCount(res.total);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname]);
  return count;
}

export function Sidebar() {
  const pathname = usePathname();
  const reviewCount = useOpenReviewCount(pathname);

  return (
    <aside className="sticky top-0 flex h-screen w-14 shrink-0 flex-col border-r bg-background md:w-56">
      <Link
        href="/"
        className="flex h-14 shrink-0 items-center gap-2.5 border-b px-4 transition-colors hover:text-foreground"
      >
        <BrandMark className="size-5 shrink-0" />
        <span className="hidden truncate text-sm font-semibold tracking-tight md:inline">
          Trace Marketplace
        </span>
      </Link>

      <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-2 py-4">
        {GROUPS.map((group) => (
          <div key={group.label} className="flex flex-col gap-0.5">
            <p className="mb-1 hidden px-2.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground md:block">
              {group.label}
            </p>
            {group.items.map((item) => (
              <NavItem
                key={item.href}
                item={item}
                active={[item.href, item.alsoMatches].some(
                  (href) => href && (pathname === href || pathname.startsWith(`${href}/`)),
                )}
                badge={item.href === "/review" ? reviewCount : undefined}
              />
            ))}
          </div>
        ))}
      </nav>

      <div className="border-t px-2 py-3">
        <NavItem
          item={{ href: "/settings", label: "Settings", icon: Settings }}
          active={pathname === "/settings" || pathname.startsWith("/settings/")}
        />
      </div>
    </aside>
  );
}
