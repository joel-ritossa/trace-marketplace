"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const NOT_ALLOWED_MESSAGE =
  "This email isn't on the allowlist for this deployment. Ask the operator to add it.";

const copy = {
  "sign-in": {
    title: "Sign in",
    subtitle: "Welcome back to Trace Marketplace.",
    cta: "Sign in",
    switchPrompt: "No account?",
    switchHref: "/auth/sign-up",
    switchLabel: "Sign up",
  },
  "sign-up": {
    title: "Create your account",
    subtitle: "Contribute, discover, and download agent traces.",
    cta: "Sign up",
    switchPrompt: "Already have an account?",
    switchHref: "/auth/sign-in",
    switchLabel: "Sign in",
  },
} as const;

export function AuthForm({ mode, notice }: { mode: keyof typeof copy; notice?: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const c = copy[mode];

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const supabase = createClient();
    const { data, error } =
      mode === "sign-up"
        ? await supabase.auth.signUp({
            email,
            password,
            options: { emailRedirectTo: `${window.location.origin}/auth/confirm` },
          })
        : await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setPending(false);
      // The allowlist trigger on auth.users surfaces through GoTrue as an
      // opaque "Database error saving new user"; translate it.
      if (error.message.includes("Database error saving")) {
        setError(NOT_ALLOWED_MESSAGE);
      } else if (error.code === "email_not_confirmed") {
        setError("Your email isn't confirmed yet. Check your inbox for the confirmation link.");
      } else {
        setError(error.message);
      }
      return;
    }
    // Email confirmation pending: sign-up succeeded but there's no session
    // until the user clicks the link we just emailed them.
    if (mode === "sign-up" && !data.session) {
      setPending(false);
      setSentTo(email);
      return;
    }
    // Sign-in succeeds at the auth layer even for non-allowlisted emails
    // (existing users); the API rejects them per-request. Check once here so
    // they get a clear message instead of a broken app.
    try {
      await getProfile();
    } catch (err) {
      if (err instanceof ApiError && err.code === "email_not_allowed") {
        await supabase.auth.signOut();
        setPending(false);
        setError(NOT_ALLOWED_MESSAGE);
        return;
      }
      // Any other API hiccup shouldn't block an authenticated user here.
    }
    setPending(false);
    router.push("/");
    router.refresh();
  }

  if (sentTo) {
    return (
      <div className="w-full max-w-sm rounded-lg border bg-background p-8">
        <h1 className="text-xl font-semibold tracking-tight">Check your inbox</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          We sent a confirmation link to <span className="text-foreground">{sentTo}</span>. Click
          it to finish creating your account.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm rounded-lg border bg-background p-8">
      <h1 className="text-xl font-semibold tracking-tight">{c.title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{c.subtitle}</p>
      {notice && <p className="mt-3 text-sm text-warning-deep">{notice}</p>}
      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            required
            minLength={6}
            autoComplete={mode === "sign-up" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-error-deep">{error}</p>}
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? "Working…" : c.cta}
        </Button>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        {c.switchPrompt}{" "}
        <Link href={c.switchHref} className="text-link hover:text-link-deep">
          {c.switchLabel}
        </Link>
      </p>
    </div>
  );
}
