import { useState, type FormEvent } from "react";
import { supabase } from "../lib/supabase";

export function LoginView({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const { error: err } = await supabase().auth.signInWithPassword({ email, password });
    setSubmitting(false);
    if (err) setError(err.message);
    else onSignedIn();
  }

  return (
    <form className="login" onSubmit={onSubmit}>
      <div>
        <h1>Trace Marketplace</h1>
        <p className="hint" style={{ marginTop: 4 }}>
          Sign in with your marketplace account. You only need to do this once.
        </p>
      </div>
      <div className="field">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          className="input"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          className="input"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {error && <p className="error-text">{error}</p>}
      <button className="btn" type="submit" disabled={submitting}>
        {submitting ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
