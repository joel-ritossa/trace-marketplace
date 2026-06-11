---
name: db-push-prod
description: Apply supabase/migrations to the production Supabase project (the trace-mp.com stack) with supabase db push. Use when asked to push migrations, run a db push, apply schema changes, or migrate the production database.
---

# Push migrations to production

Production schema lives in the hosted Supabase project (`infra/terraform.tfvars`
→ `supabase_url`). Migrations are the files in `supabase/migrations/`; never
edit one that has already been applied — add a new file instead.

## Workflow

1. Fetch the production connection string from SSM into a shell variable.
   Never print, echo, or log it. Use `export` — a plain assignment does not
   survive across separate shell invocations, and an empty `--db-url` makes
   the CLI silently fall back to a local unix socket:

   ```sh
   export DB_URL=$(aws ssm get-parameter --name /trace-marketplace/database-url \
     --with-decryption --region us-west-2 \
     --query Parameter.Value --output text)
   ```

   Requires AWS credentials with SSM read access (same profile used for
   `infra/` Terraform).

2. Dry-run and review which migrations are pending:

   ```sh
   supabase db push --db-url "$DB_URL" --dry-run
   ```

3. Show the user the pending migration list and get explicit confirmation
   before touching production.

4. Push:

   ```sh
   supabase db push --db-url "$DB_URL"
   ```

5. Verify — remote and local migration histories should match:

   ```sh
   supabase migration list --db-url "$DB_URL"
   ```

## Troubleshooting

- **Prepared-statement / pooler errors**: the SSM value is the pooler URL. If
  push fails on transaction-mode pooling (port 6543), switch to session mode
  for the push: `supabase db push --db-url "${DB_URL/:6543/:5432}"`.
- **Out-of-sync history** (migration applied manually or renamed): inspect
  with `supabase migration list --db-url "$DB_URL"`, then repair with
  `supabase migration repair --db-url "$DB_URL" --status applied <version>`.
  Confirm with the user before any repair.

## Notes

- The repo is intentionally not `supabase link`ed; everything goes through
  `--db-url` so local tooling can never target production by accident. Do
  not link it as a "fix".
- This only applies migrations. New buckets, auth settings, or dashboard
  config are separate (see `infra/README.md`).
