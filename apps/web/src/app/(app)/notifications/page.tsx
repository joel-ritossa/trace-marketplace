"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BellOff, CheckCheck } from "lucide-react";
import { Pager, usePageParam } from "@/components/shell/pager";
import { Button } from "@/components/ui/button";
import {
  listNotifications,
  markNotificationsRead,
  type Notification,
  type NotificationList,
} from "@/lib/api/notifications";
import { formatDate } from "@/lib/format";
import { useRealtimeRefetch } from "@/lib/realtime";
import { cn } from "@/lib/utils";

/** Every notification links to its object (4_pages.md): review_request →
 *  the queue filtered to the upload group; upload_failed → /uploads;
 *  subscription_match → the trace (single match) or the feed (digest).
 *  No dead ends. */
function view(n: Notification): { text: string; href: string | null } {
  const p = n.payload;
  if (n.type === "review_request") {
    // item_count counts routed events since the digest went unread, not live
    // open items (a re-run can supersede-and-recount) — phrase it as such.
    const count = Number(p.item_count ?? 0);
    return {
      text: `${count} review request${count === 1 ? "" : "s"} from upload ${p.filename ?? "?"}`,
      href: `/review?upload_id=${p.upload_id}`,
    };
  }
  if (n.type === "upload_failed") {
    return { text: `Upload ${p.filename ?? "?"} failed ingestion`, href: "/uploads" };
  }
  if (n.type === "subscription_match") {
    // The per-subscription digest (A4): trace_id survives only while the
    // count is 1, so a single match deep-links and a digest goes to the feed.
    const count = Number(p.match_count ?? 1);
    return {
      text: `${count} new trace${count === 1 ? "" : "s"} match${count === 1 ? "es" : ""} “${p.name ?? "your subscription"}”`,
      href: p.trace_id
        ? `/traces/${p.trace_id}?from=notifications`
        : `/subscriptions/${p.subscription_id}`,
    };
  }
  return { text: n.type, href: null };
}

function Row({ notification }: { notification: Notification }) {
  const { text, href } = view(notification);
  const unread = notification.read_at === null;
  const body = (
    <div className="flex items-baseline justify-between gap-4 px-4 py-3">
      <div className="flex min-w-0 items-baseline gap-2.5">
        <span
          aria-hidden
          className={cn(
            "size-1.5 shrink-0 self-center rounded-full",
            unread ? "bg-link-deep" : "bg-transparent",
          )}
        />
        <p className={cn("truncate text-sm", unread ? "font-medium" : "text-muted-foreground")}>
          {text}
        </p>
      </div>
      <time className="shrink-0 text-xs text-muted-foreground">
        {formatDate(notification.created_at)}
      </time>
    </div>
  );
  if (href === null) return <div>{body}</div>;
  return (
    <Link href={href} className="block transition-colors hover:bg-accent/50">
      {body}
    </Link>
  );
}

export default function NotificationsPage() {
  const [result, setResult] = useState<NotificationList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { page, setPage, pageSize, setPageSize } = usePageParam();

  const reload = useCallback(() => {
    listNotifications(pageSize, (page - 1) * pageSize)
      .then((res) => {
        setResult(res);
        setError(null);
      })
      .catch(() => setError("Could not load notifications. Check the API is running."));
  }, [page, pageSize]);

  useEffect(reload, [reload]);
  useRealtimeRefetch("notifications", reload);

  useEffect(() => {
    if (result && result.notifications.length === 0 && page > 1 && result.total > 0) {
      setPage(Math.max(1, Math.ceil(result.total / pageSize)));
    }
  }, [result, page, pageSize, setPage]);

  const markAllRead = () => {
    markNotificationsRead({ all: true }).then(reload).catch(reload);
  };

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Notifications</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Review requests, subscription matches, and unattended upload failures.
          </p>
        </div>
        {result !== null && result.unread_count > 0 && (
          <Button variant="outline" size="sm" onClick={markAllRead}>
            <CheckCheck data-slot="icon" />
            Mark all read
          </Button>
        )}
      </div>

      <div className="mt-6">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : result === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : result.notifications.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
            <BellOff className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">Nothing yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              You’ll hear about review requests, subscription matches, and failed CLI uploads here.
            </p>
          </div>
        ) : (
          <>
            <div className="divide-y rounded-lg border bg-background">
              {result.notifications.map((n) => (
                <Row key={n.notification_id} notification={n} />
              ))}
            </div>
            <div className="mt-4">
              <Pager page={page} pageSize={pageSize} total={result.total} onPageChange={setPage} onPageSizeChange={setPageSize} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
