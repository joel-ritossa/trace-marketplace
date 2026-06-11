"use client";

import { useState } from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { updateProfile, type Profile } from "@/lib/api/profile";

export function PrivacySection({
  profile,
  onUpdated,
}: {
  profile: Profile;
  onUpdated: (profile: Profile) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const on = profile.allow_private_llm_analysis;

  async function onToggle(checked: boolean) {
    setSaving(true);
    setError(null);
    try {
      onUpdated(await updateProfile({ allow_private_llm_analysis: checked }));
    } catch {
      setError("Could not save the setting. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h2 className="text-base font-semibold">Privacy</h2>
      <div className="mt-4 flex max-w-xl items-start justify-between gap-6 rounded-lg border bg-background p-4">
        <div>
          <Label htmlFor="llm-analysis">Allow LLM analysis of private traces</Label>
          <p className="mt-1 text-sm text-muted-foreground">
            {on
              ? "Private-trace content is sent to the configured LLM provider for labeling (outcome, failure mode, category)."
              : "Private traces get deterministic signals only. Listing a trace always analyzes it — listing is the consent act."}{" "}
            Takes effect on subsequent analysis runs.
          </p>
        </div>
        <Switch id="llm-analysis" checked={on} disabled={saving} onCheckedChange={onToggle} />
      </div>
      {error && <p className="mt-2 text-sm text-error-deep">{error}</p>}
    </section>
  );
}
