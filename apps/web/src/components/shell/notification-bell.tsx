"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { getUnreadCount } from "@/lib/api/notifications";
import { useRealtimeRefetch } from "@/lib/realtime";

/** The shell-edge bell (4_pages.md): unread badge + link to /notifications —
 *  one notifications surface, no popover. Realtime is invalidation only;
 *  mark-read updates also fire the channel, so the badge clears itself. */
export function NotificationBell() {
  const [unread, setUnread] = useState(0);

  const reload = useCallback(() => {
    getUnreadCount()
      .then(setUnread)
      .catch(() => {}); // a dead API leaves the badge stale, never broken UI
  }, []);

  useEffect(reload, [reload]);
  useRealtimeRefetch("notifications", reload);

  return (
    <Link
      href="/notifications"
      aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
      className="relative rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      <Bell className="size-4" />
      {unread > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-error-deep px-1 font-mono text-[10px] font-medium leading-none text-white">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}
