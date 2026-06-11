"use client";

import { useEffect, useState } from "react";
import { ApiKeysSection } from "@/components/settings/api-keys-section";
import { PrivacySection } from "@/components/settings/privacy-section";
import { ProfileSection } from "@/components/settings/profile-section";
import { getProfile, type Profile } from "@/lib/api/profile";

export default function SettingsPage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => setError("Could not load your profile. Check the API is running."));
  }, []);

  return (
    <div className="mx-auto w-full max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        API keys, profile, and analysis privacy.
      </p>

      <div className="mt-8 flex flex-col gap-10">
        <ApiKeysSection />
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : profile === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <>
            <ProfileSection profile={profile} onUpdated={setProfile} />
            <PrivacySection profile={profile} onUpdated={setProfile} />
          </>
        )}
      </div>
    </div>
  );
}
