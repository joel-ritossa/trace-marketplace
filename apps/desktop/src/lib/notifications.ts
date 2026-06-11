import { apiFetch } from "./api";

// Types mirror services/api/app/schemas/notification.py and the web's
// lib/api/notifications.ts — keep in sync. The desktop only reads
// notifications to drive native popups; the web's /notifications page owns
// the feed and read-state.

export type NotificationType = "review_request" | "subscription_match" | "upload_failed";

export type Notification = {
  notification_id: string;
  type: NotificationType;
  // Type-specific; always enough to build the link target.
  payload: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
};

export type NotificationList = {
  notifications: Notification[];
  total: number;
  unread_count: number;
};

export async function listNotifications(limit = 50, offset = 0): Promise<NotificationList> {
  return apiFetch<NotificationList>(`/v1/notifications?limit=${limit}&offset=${offset}`);
}

/** Display text + web-app path per type — mirrors the web notifications
 *  page's view() so both surfaces phrase events identically. */
export function describeNotification(n: Notification): { text: string; webPath: string | null } {
  const p = n.payload;
  if (n.type === "review_request") {
    const count = Number(p.item_count ?? 0);
    return {
      text: `${count} review request${count === 1 ? "" : "s"} from upload ${p.filename ?? "?"}`,
      webPath: `/review?upload_id=${p.upload_id}`,
    };
  }
  if (n.type === "upload_failed") {
    return { text: `Upload ${p.filename ?? "?"} failed ingestion`, webPath: "/uploads" };
  }
  if (n.type === "subscription_match") {
    const count = Number(p.match_count ?? 1);
    return {
      text: `${count} new trace${count === 1 ? "" : "s"} match${count === 1 ? "es" : ""} “${p.name ?? "your subscription"}”`,
      webPath: p.trace_id ? `/traces/${p.trace_id}` : `/subscriptions/${p.subscription_id}`,
    };
  }
  return { text: n.type, webPath: null };
}
