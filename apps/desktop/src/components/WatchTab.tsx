import { useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { detectHarnessFolders, toWatchRoots } from "../lib/harnesses";
import type { Settings } from "../lib/settings";
import { supabase } from "../lib/supabase";
import { openSyncCache } from "../lib/sync/cache";
import { Watcher, type WatchEvent } from "../lib/sync/watcher";

type LogLine = { id: number; at: string; text: string; tone: "ok" | "err" | "dim" };

let nextLineId = 0;

function logTime(): string {
  return new Date().toLocaleTimeString(undefined, { hour12: false });
}

export function WatchTab({
  settings,
  onChange,
}: {
  settings: Settings;
  onChange: (next: Settings) => void;
}) {
  const [watching, setWatching] = useState(false);
  const [counts, setCounts] = useState({ synced: 0, skipped: 0, failed: 0 });
  const [log, setLog] = useState<LogLine[]>([]);
  const watcherRef = useRef<Watcher | null>(null);

  function appendLog(text: string, tone: LogLine["tone"]) {
    // Newest first, capped so a long-lived watch doesn't grow forever.
    setLog((lines) => [{ id: nextLineId++, at: logTime(), text, tone }, ...lines].slice(0, 500));
  }

  function onEvent(event: WatchEvent) {
    if (event.type === "status") {
      appendLog(event.message, "dim");
      return;
    }
    const { kind, detail } = event.outcome;
    appendLog(
      `${event.path} → ${detail}`,
      kind === "uploaded" ? "ok" : kind === "failed" ? "err" : "dim",
    );
    if (watcherRef.current) setCounts({ ...watcherRef.current.counts });
  }

  async function start() {
    if (watcherRef.current || settings.folders.length === 0) return;
    const roots = await toWatchRoots(settings.folders);
    // Synced marks persist per server + account so restarts skip the
    // upload-then-409 round-trip for files already on this backend.
    const {
      data: { session },
    } = await supabase().auth.getSession();
    const store = await openSyncCache(settings.apiUrl, session?.user.id ?? "anonymous");
    const watcher = new Watcher(roots, settings.sinceHours, onEvent, store);
    watcherRef.current = watcher;
    setWatching(true);
    setCounts({ synced: 0, skipped: 0, failed: 0 });
    watcher
      .run()
      .catch((err) => appendLog(`watcher stopped: ${err}`, "err"))
      .finally(() => {
        watcherRef.current = null;
        setWatching(false);
        appendLog("watch stopped", "dim");
      });
  }

  function stop() {
    watcherRef.current?.stop();
  }

  async function addFolders() {
    const picked = await open({ directory: true, multiple: true });
    if (!picked) return;
    const folders = [...new Set([...settings.folders, ...picked])];
    onChange({ ...settings, folders });
  }

  async function detectHarnesses() {
    const detected = await detectHarnessFolders();
    const fresh = detected.filter((d) => !settings.folders.includes(d));
    if (fresh.length > 0) onChange({ ...settings, folders: [...settings.folders, ...fresh] });
    appendLog(
      fresh.length > 0
        ? `added ${fresh.length} harness folder${fresh.length === 1 ? "" : "s"}: ${fresh.join(", ")}`
        : "no new harness session folders found (~/.codex/sessions, ~/.claude/projects, ~/.cursor/projects)",
      "dim",
    );
  }

  function removeFolder(folder: string) {
    onChange({ ...settings, folders: settings.folders.filter((f) => f !== folder) });
  }

  const foldersLocked = watching;

  return (
    <div className="page fill">
      <div className="row spread">
        <div>
          <h1>Watch &amp; sync</h1>
          <p className="hint" style={{ marginTop: 2 }}>
            Uploads every new .json/.jsonl trace or session file under the watched folders.
            Re-syncing is always safe — the server dedupes by content.
          </p>
        </div>
        {watching ? (
          <button className="btn outline" onClick={stop}>
            Stop watching
          </button>
        ) : (
          <button className="btn" onClick={start} disabled={settings.folders.length === 0}>
            Start watching
          </button>
        )}
      </div>

      <section className="card">
        <div className="row spread">
          <h2>Folders</h2>
          <div className="row">
            <button className="btn outline small" onClick={detectHarnesses} disabled={foldersLocked}>
              Detect agent sessions
            </button>
            <button className="btn outline small" onClick={addFolders} disabled={foldersLocked}>
              Add folder…
            </button>
          </div>
        </div>
        {settings.folders.length === 0 ? (
          <p className="hint">
            Nothing watched yet. Add a folder, or detect your coding agents’ session logs
            (Codex, Claude Code, Cursor).
          </p>
        ) : (
          <div className="list">
            {settings.folders.map((folder) => (
              <div key={folder} className="row spread" style={{ padding: "6px 0" }}>
                <code>{folder}</code>
                <button
                  className="link-btn"
                  onClick={() => removeFolder(folder)}
                  disabled={foldersLocked}
                >
                  remove
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="row">
          <label className="hint" htmlFor="since-hours">
            Only files modified in the last
          </label>
          <input
            id="since-hours"
            className="input"
            style={{ width: 70 }}
            type="number"
            min={1}
            disabled={foldersLocked}
            value={settings.sinceHours ?? ""}
            placeholder="∞"
            onChange={(e) => {
              const value = e.target.value === "" ? null : Number(e.target.value);
              onChange({ ...settings, sinceHours: value });
            }}
          />
          <span className="hint">hours (clear to sync everything)</span>
        </div>
      </section>

      <section className="card fill">
        <div className="row spread">
          <h2>Activity</h2>
          <span className="hint mono">
            synced {counts.synced} · skipped {counts.skipped} · failed {counts.failed}
          </span>
        </div>
        {log.length === 0 ? (
          <p className="hint">{watching ? "Watching…" : "Not watching."}</p>
        ) : (
          <div className="log fill">
            {log.map((line) => (
              <div key={line.id} className={line.tone}>
                <span className="log-time">{line.at}</span>
                {line.text}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
