import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { openUrl } from "@tauri-apps/plugin-opener";
import { LoginView } from "./components/LoginView";
import { ReviewTab } from "./components/ReviewTab";
import { SettingsTab } from "./components/SettingsTab";
import { WatchTab } from "./components/WatchTab";
import { setApiBaseUrl } from "./lib/api";
import { detectHarnessFolders } from "./lib/harnesses";
import { describeNotification, listNotifications } from "./lib/notifications";
import { nativeNotify, onNativeNotificationClick } from "./lib/notify";
import { useRealtimeRefetch } from "./lib/realtime";
import {
  DEFAULT_SETTINGS,
  loadSavedSettings,
  saveSettings,
  type Settings,
} from "./lib/settings";
import { initSupabase } from "./lib/supabase";
import { clearSyncCache } from "./lib/sync/cache";
import { initTray, setTrayCount, showWindow } from "./lib/tray";

const UNREAD_POLL_MS = 60_000;

type Phase = "booting" | "login" | "ready";
type Tab = "watch" | "review" | "settings";

/** Native-popup driver: realtime invalidation with a fallback poll; fires one
 *  native notification per unread increase, worded like the newest unread
 *  item. Clicking lands on the Review tab for review requests and the web
 *  app for everything else — the desktop has no notification feed of its own
 *  (the web's /notifications page owns that surface). */
function useNotificationPopups() {
  const previous = useRef<number | null>(null);

  const reload = useCallback(() => {
    listNotifications(1, 0)
      .then(({ unread_count, notifications }) => {
        const prev = previous.current;
        previous.current = unread_count;
        if (prev !== null && unread_count > prev) {
          const newest = notifications[0];
          const fresh = newest !== undefined && newest.read_at === null;
          if (fresh && newest.type === "review_request") {
            void nativeNotify("Trace Marketplace", describeNotification(newest).text, {
              kind: "review",
            });
          } else if (fresh) {
            const { text, webPath } = describeNotification(newest);
            void nativeNotify("Trace Marketplace", text, {
              kind: "web",
              path: webPath ?? "/notifications",
            });
          } else {
            void nativeNotify("Trace Marketplace", `${unread_count} unread notifications`, {
              kind: "web",
              path: "/notifications",
            });
          }
        }
      })
      .catch(() => {}); // a dead API skips a popup, never broken UI
  }, []);

  useEffect(() => {
    reload();
    const timer = setInterval(reload, UNREAD_POLL_MS);
    return () => clearInterval(timer);
  }, [reload]);
  useRealtimeRefetch("notifications", reload);
}

function Shell({
  settings,
  email,
  onSettingsChange,
}: {
  settings: Settings;
  email: string | null;
  onSettingsChange: (next: Settings) => void;
}) {
  const [tab, setTab] = useState<Tab>("watch");
  const [openReviews, setOpenReviews] = useState(0);
  useNotificationPopups();

  // The tray title mirrors the Review badge: open items needing judgment,
  // not unread announcements.
  useEffect(() => {
    void setTrayCount(openReviews);
  }, [openReviews]);

  // A click on a native notification surfaces the Review tab or the web app.
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let stale = false;
    void onNativeNotificationClick((action) => {
      if (action.kind === "web") {
        void openUrl(`${settings.webUrl}${action.path}`);
        return;
      }
      void showWindow();
      setTab("review");
    }).then((cleanup) => {
      if (stale) cleanup();
      else unlisten = cleanup;
    });
    return () => {
      stale = true;
      unlisten?.();
    };
  }, [settings.webUrl]);

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "watch", label: "Watch" },
    { id: "review", label: "Review", count: openReviews },
    { id: "settings", label: "Settings" },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Trace Marketplace</span>
        <nav className="tabs">
          {tabs.map(({ id, label, count }) => (
            <button key={id} className="tab" data-active={tab === id} onClick={() => setTab(id)}>
              {label}
              {count !== undefined && count > 0 && <span className="count">{count}</span>}
            </button>
          ))}
        </nav>
        <span className="who">{email ?? ""}</span>
      </header>
      {/* Tabs stay mounted so the watcher and listeners survive switching. */}
      <main className="content">
        <div
          style={{
            display: tab === "watch" ? "flex" : "none",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
          }}
        >
          <WatchTab settings={settings} onChange={onSettingsChange} />
        </div>
        <div style={{ display: tab === "review" ? undefined : "none" }}>
          <ReviewTab webUrl={settings.webUrl} onOpenCount={setOpenReviews} />
        </div>
        <div style={{ display: tab === "settings" ? undefined : "none" }}>
          <SettingsTab settings={settings} email={email} />
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("booting");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [bootStage, setBootStage] = useState("starting");

  useEffect(() => {
    let unlistenClose: (() => void) | undefined;
    let unsubscribeAuth: (() => void) | undefined;

    (async () => {
      // Closing the window hides to the tray; the tray click brings it back.
      setBootStage("wiring window");
      unlistenClose = await getCurrentWindow().onCloseRequested(async (event) => {
        event.preventDefault();
        await getCurrentWindow().hide();
      });
      setBootStage("creating tray");
      await initTray();

      // First run: seed the watched folders with detected harness session
      // dirs (~/.codex/sessions, ~/.claude/projects, ~/.cursor/projects).
      setBootStage("loading settings");
      let loaded = await loadSavedSettings();
      if (loaded === null) {
        setBootStage("detecting harness folders");
        loaded = { ...DEFAULT_SETTINGS, folders: await detectHarnessFolders() };
        await saveSettings(loaded);
      }
      setApiBaseUrl(loaded.apiUrl);
      setBootStage("restoring session");
      const client = await initSupabase(loaded);
      setSettings(loaded);

      const {
        data: { session },
      } = await client.auth.getSession();
      setEmail(session?.user.email ?? null);
      setPhase(session ? "ready" : "login");

      const {
        data: { subscription },
      } = client.auth.onAuthStateChange((event, next) => {
        setEmail(next?.user.email ?? null);
        if (next === null) {
          setPhase("login");
          void setTrayCount(0);
        }
        // The next sign-in may be a different account or a re-seeded backend,
        // so stale synced marks must not suppress uploads.
        if (event === "SIGNED_OUT") void clearSyncCache();
      });
      unsubscribeAuth = () => subscription.unsubscribe();
    })().catch((err) => setBootError(String(err)));

    return () => {
      unlistenClose?.();
      unsubscribeAuth?.();
    };
  }, []);

  async function persistSettings(next: Settings) {
    setSettings(next);
    await saveSettings(next);
  }

  if (bootError !== null) {
    return (
      <div className="app" style={{ alignItems: "center", justifyContent: "center" }}>
        <p className="error-text">Failed to start: {bootError}</p>
      </div>
    );
  }
  if (phase === "booting" || settings === null) {
    return (
      <div className="app" style={{ alignItems: "center", justifyContent: "center" }}>
        <p className="hint">{bootStage}…</p>
      </div>
    );
  }
  if (phase === "login") {
    return (
      <div className="app">
        <LoginView onSignedIn={() => setPhase("ready")} />
      </div>
    );
  }
  return <Shell settings={settings} email={email} onSettingsChange={persistSettings} />;
}
