import { apiFetch } from "@/lib/api/client";

// Types mirror services/api/app/schemas/profile.py — keep in sync.

export type Profile = {
  id: string;
  email: string | null;
  display_name: string | null;
  allow_private_llm_analysis: boolean;
  created_at: string;
};

export type ProfileUpdate = {
  display_name?: string;
  allow_private_llm_analysis?: boolean;
};

export async function getProfile(): Promise<Profile> {
  return apiFetch<Profile>("/v1/profile");
}

export async function updateProfile(update: ProfileUpdate): Promise<Profile> {
  return apiFetch<Profile>("/v1/profile", {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}
