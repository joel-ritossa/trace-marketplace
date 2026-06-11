"use client";

import { useState } from "react";
import { TASK_CATEGORY_GROUPS, humanize } from "@/components/review/taxonomy";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { updateProfile, type Profile } from "@/lib/api/profile";

export function TaskScopeSection({
  profile,
  onUpdated,
}: {
  profile: Profile;
  onUpdated: (profile: Profile) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = new Set(profile.task_categories);

  async function onToggle(value: string, checked: boolean) {
    const next = new Set(selected);
    if (checked) next.add(value);
    else next.delete(value);
    setSaving(true);
    setError(null);
    try {
      onUpdated(await updateProfile({ task_categories: [...next].sort() }));
    } catch {
      setError("Could not save the setting. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h2 className="text-base font-semibold">Task scope</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The kinds of tasks your agents work on. The analysis judge only assigns categories from
        your selection (plus “other”), which keeps its labels decisive.{" "}
        {selected.size === 0
          ? "Nothing selected = the full taxonomy is considered."
          : `${selected.size} selected.`}{" "}
        Applies to subsequent analysis runs.
      </p>
      <div className="mt-4 flex flex-col gap-5 rounded-lg border bg-background p-4">
        {TASK_CATEGORY_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {group.label}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
              {group.values.map((value) => (
                <div key={value} className="flex items-center gap-2">
                  <Checkbox
                    id={`scope-${value}`}
                    checked={selected.has(value)}
                    disabled={saving}
                    onCheckedChange={(checked) => onToggle(value, checked === true)}
                  />
                  <Label htmlFor={`scope-${value}`} className="text-sm font-normal capitalize">
                    {humanize(value)}
                  </Label>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      {error && <p className="mt-2 text-sm text-error-deep">{error}</p>}
    </section>
  );
}
