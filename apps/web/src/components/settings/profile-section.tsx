"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { updateProfile, type Profile } from "@/lib/api/profile";

export function ProfileSection({
  profile,
  onUpdated,
}: {
  profile: Profile;
  onUpdated: (profile: Profile) => void;
}) {
  const [name, setName] = useState(profile.display_name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty = name.trim() !== (profile.display_name ?? "") && name.trim().length > 0;

  async function onSave() {
    setSaving(true);
    setError(null);
    try {
      onUpdated(await updateProfile({ display_name: name.trim() }));
    } catch {
      setError("Could not save the display name. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h2 className="text-base font-semibold">Profile</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">
        Your display name appears on marketplace cards for traces you list.
      </p>
      <div className="mt-4 max-w-md">
        <Label htmlFor="display-name">Display name</Label>
        <div className="mt-2 flex items-center gap-2">
          <Input
            id="display-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && dirty && !saving) void onSave();
            }}
          />
          <Button size="sm" disabled={!dirty || saving} onClick={onSave}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
        {error && <p className="mt-2 text-sm text-error-deep">{error}</p>}
      </div>
    </section>
  );
}
