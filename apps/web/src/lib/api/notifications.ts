import { apiFetch, apiSend } from "@/lib/api/client";

// Types mirror services/api/app/schemas/notification.py — keep in sync.

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

export async function getUnreadCount(): Promise<number> {
  const { unread_count } = await listNotifications(1, 0);
  return unread_count;
}

export async function markNotificationsRead(
  body: { ids: string[] } | { all: true },
): Promise<void> {
  await apiSend("/v1/notifications/read", { method: "POST", body: JSON.stringify(body) });
}
