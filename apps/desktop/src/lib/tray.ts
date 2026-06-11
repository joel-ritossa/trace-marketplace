import { defaultWindowIcon } from "@tauri-apps/api/app";
import { TrayIcon } from "@tauri-apps/api/tray";
import { getCurrentWindow } from "@tauri-apps/api/window";

// The tray is the app's persistent presence: closing the window hides it
// (wired in App.tsx); a left-click on the tray brings it back. The title
// carries the open-review-item count next to the icon.

let trayPromise: Promise<TrayIcon> | null = null;

export async function showWindow(): Promise<void> {
  const window = getCurrentWindow();
  await window.show();
  await window.unminimize();
  await window.setFocus();
}

async function getOrCreateTray(): Promise<TrayIcon> {
  // Vite dev reloads / StrictMode double-effects re-enter this; the single
  // promise plus the id lookup keep it to one tray per app process.
  const existing = await TrayIcon.getById("main");
  if (existing !== null) return existing;
  return TrayIcon.new({
    id: "main",
    icon: (await defaultWindowIcon()) ?? undefined,
    tooltip: "Trace Marketplace",
    action: (event) => {
      if (event.type === "Click" && event.button === "Left" && event.buttonState === "Up") {
        void showWindow();
      }
    },
  });
}

export async function initTray(): Promise<void> {
  if (trayPromise === null) trayPromise = getOrCreateTray();
  await trayPromise;
}

export async function setTrayCount(count: number): Promise<void> {
  const tray = await (trayPromise ?? Promise.resolve(null));
  await tray?.setTitle(count > 0 ? String(count) : null);
}
