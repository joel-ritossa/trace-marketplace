"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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

export function AuthForm({ mode }: { mode: keyof typeof copy }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const c = copy[mode];

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const supabase = createClient();
    const { error } =
      mode === "sign-up"
        ? await supabase.auth.signUp({ email, password })
        : await supabase.auth.signInWithPassword({ email, password });
    setPending(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <div className="w-full max-w-sm rounded-lg border bg-background p-8">
      <h1 className="text-xl font-semibold tracking-tight">{c.title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{c.subtitle}</p>
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
