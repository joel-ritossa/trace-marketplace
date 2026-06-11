import {
  isPermissionGranted,
  onNotificationClicked,
  requestPermission,
  sendNotification,
} from "@choochmeque/tauri-plugin-notifications-api";

/** Where a click on a native notification should land: the in-app Review
 *  tab (the desktop's only actionable surface) or a web-app page. */
export type NotifyAction = { kind: "review" } | { kind: "web"; path: string };

let granted: boolean | null = null;

/** Best-effort: in `tauri dev` the plugin isn't registered (no .app bundle —
 *  see src-tauri/lib.rs), so every call rejects and notifications are a no-op. */
export async function nativeNotify(
  title: string,
  body: string,
  action: NotifyAction,
): Promise<void> {
  try {
    if (granted === null) {
      granted = await isPermissionGranted();
      if (!granted) granted = (await requestPermission()) === "granted";
    }
    if (granted) {
      await sendNotification({
        title,
        body,
        extra: action.kind === "web" ? { target: "web", path: action.path } : { target: "review" },
      });
    }
  } catch {
    // plugin unavailable (dev build) — skip silently
  }
}

/** Fires when the user clicks a native notification; resolves to an unlisten
 *  function (a no-op when the plugin is unavailable). */
export async function onNativeNotificationClick(
  callback: (action: NotifyAction) => void,
): Promise<() => void> {
  try {
    const listener = await onNotificationClicked((event) => {
      const data = event.data as { target?: unknown; path?: unknown } | undefined;
      if (data?.target === "web" && typeof data.path === "string") {
        callback({ kind: "web", path: data.path });
      } else {
        callback({ kind: "review" });
      }
    });
    return () => void listener.unregister();
  } catch {
    return () => {};
  }
}
