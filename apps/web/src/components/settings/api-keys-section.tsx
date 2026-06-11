"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  type ApiKey,
  type ApiKeyCreated,
} from "@/lib/api/api-keys";
import { publicEnv } from "@/lib/env";
import { formatDate } from "@/lib/format";

// Embed the API origin this deployment actually serves, so the copied
// command works verbatim against local and hosted stacks alike.
function cliSnippet(key: string): string {
  return `TRACE_API_URL=${publicEnv.apiUrl} TRACE_API_KEY=${key} trace-sync sync ./traces`;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="outline"
      size="icon-sm"
      aria-label={label}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <Check /> : <Copy />}
    </Button>
  );
}

/** Shown exactly once after mint; dismissed only by explicit user action. */
function MintedKeyReveal({ minted, onDismiss }: { minted: ApiKeyCreated; onDismiss: () => void }) {
  return (
    <div className="rounded-lg border bg-accent/40 p-4">
      <p className="text-sm font-medium">
        Key “{minted.name}” created — copy it now, you won’t see it again.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <code className="flex-1 truncate rounded-md border bg-background px-3 py-2 font-mono text-sm">
          {minted.api_key}
        </code>
        <CopyButton text={minted.api_key} label="Copy API key" />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">Use it with the sync CLI:</p>
      <div className="mt-1 flex items-center gap-2">
        <code className="flex-1 overflow-x-auto rounded-md border bg-background px-3 py-2 font-mono text-xs whitespace-nowrap">
          {cliSnippet(minted.api_key)}
        </code>
        <CopyButton text={cliSnippet(minted.api_key)} label="Copy CLI command" />
      </div>
      <div className="mt-4">
        <Button size="sm" onClick={onDismiss}>
          I’ve copied the key
        </Button>
      </div>
    </div>
  );
}

export function ApiKeysSection() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mintOpen, setMintOpen] = useState(false);
  const [mintName, setMintName] = useState("");
  const [minting, setMinting] = useState(false);
  const [minted, setMinted] = useState<ApiKeyCreated | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);

  const reload = useCallback(() => {
    listApiKeys()
      .then((res) => {
        setKeys(res.api_keys);
        setError(null);
      })
      .catch(() => setError("Could not load API keys. Check the API is running."));
  }, []);

  useEffect(reload, [reload]);

  async function onMint() {
    setMinting(true);
    try {
      const created = await createApiKey(mintName.trim());
      setMinted(created);
      setMintOpen(false);
      setMintName("");
      reload();
    } catch {
      setError("Could not create the key. Try again.");
    } finally {
      setMinting(false);
    }
  }

  async function onRevoke(key: ApiKey) {
    try {
      await revokeApiKey(key.api_key_id);
      setRevokeTarget(null);
      reload();
    } catch {
      setError("Could not revoke the key. Try again.");
    }
  }

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">API keys</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Upload-only keys for the <code className="font-mono text-xs">trace-sync</code> CLI.
          </p>
        </div>
        {keys !== null && keys.length > 0 && (
          <Button size="sm" onClick={() => setMintOpen(true)}>
            Create key
          </Button>
        )}
      </div>

      {minted && (
        <div className="mt-4">
          <MintedKeyReveal minted={minted} onDismiss={() => setMinted(null)} />
        </div>
      )}

      <div className="mt-4">
        {error ? (
          <p className="text-sm text-error-deep">{error}</p>
        ) : keys === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : keys.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border bg-background px-6 py-12 text-center">
            <KeyRound className="size-8 text-muted-foreground" strokeWidth={1.5} />
            <p className="mt-4 text-sm font-medium">No API keys yet</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              Create a key to sync traces from your terminal with the CLI — it can only upload,
              nothing else.
            </p>
            <Button size="sm" className="mt-4" onClick={() => setMintOpen(true)}>
              Create key
            </Button>
            <p className="mt-3 text-xs text-muted-foreground">
              CLI setup: <code className="font-mono">docs/demos/cli-sync.md</code> in the repo.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border bg-background">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 font-medium">Name</th>
                  <th className="px-4 py-2.5 font-medium">Key</th>
                  <th className="px-4 py-2.5 font-medium">Scope</th>
                  <th className="px-4 py-2.5 font-medium">Created</th>
                  <th className="px-4 py-2.5 font-medium">Last used</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => {
                  const revoked = key.revoked_at !== null;
                  return (
                    <tr
                      key={key.api_key_id}
                      className={`border-b last:border-b-0 ${revoked ? "text-muted-foreground" : ""}`}
                    >
                      <td className={`px-4 py-2.5 font-medium ${revoked ? "line-through" : ""}`}>
                        {key.name}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs">{key.key_display}</td>
                      <td className="px-4 py-2.5 text-xs">upload-only</td>
                      <td className="px-4 py-2.5 font-mono text-xs">{formatDate(key.created_at)}</td>
                      <td className="px-4 py-2.5 font-mono text-xs">
                        {key.last_used_at ? formatDate(key.last_used_at) : "never used"}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {revoked ? (
                          <span className="text-xs">revoked {formatDate(key.revoked_at!)}</span>
                        ) : (
                          <Button variant="ghost" size="sm" onClick={() => setRevokeTarget(key)}>
                            Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Dialog open={mintOpen} onOpenChange={setMintOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API key</DialogTitle>
            <DialogDescription>
              The key can upload traces and check upload status — nothing else. You’ll see the
              full key exactly once.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="key-name">Name</Label>
            <Input
              id="key-name"
              placeholder="e.g. laptop sync"
              value={mintName}
              onChange={(e) => setMintName(e.target.value)}
              onKeyDown={(e) => {
                // !minting: Enter while the request is in flight must not double-mint.
                if (e.key === "Enter" && mintName.trim() && !minting) void onMint();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMintOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!mintName.trim() || minting} onClick={onMint}>
              {minting ? "Creating…" : "Create key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={revokeTarget !== null} onOpenChange={(open) => !open && setRevokeTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke “{revokeTarget?.name}”?</DialogTitle>
            <DialogDescription>
              Syncs using this key will stop working immediately. This can’t be undone; traces
              already uploaded are unaffected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => revokeTarget && onRevoke(revokeTarget)}>
              Revoke key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
