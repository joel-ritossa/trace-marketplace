import { useState } from "react";
import { supabase } from "../lib/supabase";
import type { Settings } from "../lib/settings";
import { saveSettings } from "../lib/settings";

export function SettingsTab({
  settings,
  email,
}: {
  settings: Settings;
  email: string | null;
}) {
  const [form, setForm] = useState({
    apiUrl: settings.apiUrl,
    supabaseUrl: settings.supabaseUrl,
    supabaseAnonKey: settings.supabaseAnonKey,
    webUrl: settings.webUrl,
  });
  const [saving, setSaving] = useState(false);

  const dirty =
    form.apiUrl !== settings.apiUrl ||
    form.supabaseUrl !== settings.supabaseUrl ||
    form.supabaseAnonKey !== settings.supabaseAnonKey ||
    form.webUrl !== settings.webUrl;

  async function saveAndReload() {
    setSaving(true);
    await saveSettings({ ...settings, ...form });
    // Connection settings feed the singleton clients; a reload re-bootstraps.
    window.location.reload();
  }

  async function signOut() {
    await supabase().auth.signOut();
  }

  const field = (key: keyof typeof form, label: string) => (
    <div className="field">
      <label htmlFor={key}>{label}</label>
      <input
        id={key}
        className="input"
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
    </div>
  );

  return (
    <div className="page">
      <div>
        <h1>Settings</h1>
        <p className="hint" style={{ marginTop: 2 }}>
          Defaults match the local stack; point these at a deployed marketplace to use it instead.
        </p>
      </div>

      <section className="card">
        <h2>Connection</h2>
        {field("apiUrl", "API URL")}
        {field("supabaseUrl", "Supabase URL")}
        {field("supabaseAnonKey", "Supabase anon key (public)")}
        {field("webUrl", "Web app URL (for deep links)")}
        <div className="row">
          <button className="btn" disabled={!dirty || saving} onClick={saveAndReload}>
            Save &amp; reconnect
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Account</h2>
        <div className="row spread">
          <span className="hint">{email ?? "Signed in"}</span>
          <button className="btn outline small" onClick={signOut}>
            Sign out
          </button>
        </div>
      </section>
    </div>
  );
}
