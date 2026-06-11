import { apiFetch, apiSend } from "@/lib/api/client";

// Types mirror services/api/app/schemas/api_key.py — keep in sync.

export type ApiKey = {
  api_key_id: string;
  name: string;
  key_display: string;
  scope: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

// The only payload that ever carries the plaintext key (shown once at mint).
export type ApiKeyCreated = {
  api_key: string;
  api_key_id: string;
  name: string;
  key_display: string;
  scope: string;
  created_at: string;
};

export type ApiKeyList = { api_keys: ApiKey[] };

export async function createApiKey(name: string): Promise<ApiKeyCreated> {
  return apiFetch<ApiKeyCreated>("/v1/api-keys", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function listApiKeys(): Promise<ApiKeyList> {
  return apiFetch<ApiKeyList>("/v1/api-keys");
}

export async function revokeApiKey(apiKeyId: string): Promise<void> {
  await apiSend(`/v1/api-keys/${apiKeyId}`, { method: "DELETE" });
}
