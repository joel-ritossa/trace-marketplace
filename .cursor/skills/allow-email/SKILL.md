---
name: allow-email
description: Add an email or domain to the sign-up/sign-in allowlist (allowed_emails table), locally or on production. Use when asked to allowlist, whitelist, or grant access to an email or domain, locally or on the deployed trace-mp.com stack.
---

# Allowlist an email

Auth is gated by the `allowed_emails` table (migration 6 blocks sign-up via
trigger; `app/auth.py` checks sign-in per request). An entry is a full email
(`user@example.com`) or a whole domain (`@example.com`). Entries are
lowercased; inserts are idempotent.

## Local stack

```sh
make allow EMAIL=user@example.com    # or EMAIL=@example.com
```

Targets whatever `.env` / `.env.local` point at (the Compose stack by default).

## Production (trace-mp.com)

Credentials live in git-ignored `.env.production`. Export them, then run the
same target:

```sh
set -a; source .env.production; set +a
make allow EMAIL=user@example.com
```

`tools/_stack.py:load_env()` deliberately does NOT read `.env.production` —
production is opt-in via explicit export so seed/smoke scripts can never
target it by accident. Do not "fix" this.

### If `.env.production` is missing

Regenerate it without echoing the key into the transcript:

```sh
{
  echo "SUPABASE_URL=$(awk -F'"' '/supabase_url/ {print $2}' infra/terraform.tfvars)"
  echo "SUPABASE_SERVICE_ROLE_KEY=$(aws ssm get-parameter \
    --name /trace-marketplace/supabase-service-role-key \
    --with-decryption --region us-west-2 \
    --query Parameter.Value --output text)"
} > .env.production
```

Requires AWS credentials with SSM read access (same profile used for
`infra/` Terraform). Never print, cat, or commit the service-role key.

## Verify

On success the tool prints `allowlisted <entry>`. To list current entries
(service-role PostgREST, run with the env exported as above):

```sh
curl -s "$SUPABASE_URL/rest/v1/allowed_emails?select=entry,created_at" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

There is no remove command; delete a row the same way with
`curl -X DELETE ".../allowed_emails?entry=eq.<entry>"` plus the same headers.
