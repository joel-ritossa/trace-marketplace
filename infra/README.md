# AWS deployment

Terraform for running Trace Marketplace on AWS. Supabase (Postgres, auth,
storage) stays on supabase.com — only the four app containers run in AWS.

## Architecture

```
Route53 ── ACM ── ALB (WAF, HTTPS only) ── /v1/* ─▶ api  (ECS Fargate)
                                        └─ /*   ─▶ web  (ECS Fargate)
                                                    worker, scheduler (no ingress)
                                                    ElastiCache Redis (TLS)
                                                          │
                                              Supabase Cloud (DB/auth/storage)
```

- One VPC, two AZs. ALB in public subnets; all tasks and Redis in private
  subnets behind NAT. VPC endpoints (ECR, S3, Logs, SSM) keep pulls and
  secrets off the public internet.
- Path-based routing: everything under `/v1/*` goes to the API, the rest to
  the web app. One domain, one cert, no CORS.
- Secrets (`DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) live in SSM Parameter
  Store; Terraform owns the parameter shells, never the values.
- Deploys run from GitHub Actions via OIDC (no stored AWS keys): build both
  images, push `:git-sha` tags, register new task-definition revisions, wait
  for stability. Terraform owns the initial task definitions and ignores
  drift after that.

## Bootstrap (one time)

1. **Supabase**: create a project at supabase.com. Note the project URL, anon
   key, service-role key, and the *pooler* connection string (Settings →
   Database). Apply migrations: `supabase link --project-ref <ref> && supabase db push`.
2. **Domain**: register the domain in the Route53 console (registration
   auto-creates the hosted zone Terraform looks up).
3. **State bucket** (name must match `backend.tf`):

   ```sh
   aws s3 mb s3://trace-marketplace-tfstate --region us-west-2
   aws s3api put-bucket-versioning --bucket trace-marketplace-tfstate \
     --versioning-configuration Status=Enabled
   ```

4. **Apply**:

   ```sh
   cd infra
   cp terraform.tfvars.example terraform.tfvars   # fill in domain + supabase URL
   terraform init
   terraform apply
   ```

5. **Secrets** (values never touch Terraform state beyond the placeholder):

   ```sh
   aws ssm put-parameter --name /trace-marketplace/database-url \
     --type SecureString --overwrite --value '<supabase pooler url>'
   aws ssm put-parameter --name /trace-marketplace/supabase-service-role-key \
     --type SecureString --overwrite --value '<service role key>'
   ```

6. **Allowlist sign-in emails** (auth is restricted to the `allowed_emails`
   table — without this nobody can sign up or sign in). Entries are full
   addresses or whole domains:

   ```sh
   SUPABASE_URL=https://<ref>.supabase.co \
   SUPABASE_SERVICE_ROLE_KEY=<service role key> \
   make allow EMAIL=you@example.com    # or EMAIL=@example.com
   ```

7. **GitHub Actions variables** (repo → Settings → Variables):
   - `AWS_DEPLOY_ROLE_ARN` — from `terraform output github_deploy_role_arn`
   - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `APP_URL` — `https://<domain>`
8. **First deploy**: push to `main` (or run the Deploy workflow manually).
   ECS services flap until the first images land; the workflow waits for
   stability.
9. **Supabase auth** (dashboard, Authentication section):
   - *URL Configuration*: Site URL `https://<domain>`; add
     `https://<domain>/auth/confirm` to the redirect URL list — without it
     confirmation links bounce to localhost.
   - *SMTP Settings*: enable custom SMTP so confirmation emails reach real
     users (Supabase's built-in mailer only delivers to your own org members,
     at 2/hour). For Mailgun: host `smtp.mailgun.org`, port `587`, username
     and password from an SMTP credential on the sending domain (Mailgun →
     Sending → Domain settings → SMTP credentials), sender e.g.
     `no-reply@<mailgun domain>`.
   - *Sign In / Up → Email*: turn on "Confirm email". Bump the email rate
     limit (Rate Limits page) if the default 30/hour is ever tight.

## Day 2

- **Deploy**: push to `main`. Rollback: re-run the workflow from a good
  commit (`workflow_dispatch`), or `aws ecs update-service --cluster
  trace-marketplace --service api --task-definition trace-marketplace-api:<rev>`.
- **Logs**: CloudWatch `/ecs/trace-marketplace/{api,worker,scheduler,web}`.
- **Infra changes**: edit `infra/`, `terraform plan` / `apply`. Task
  definition image churn from CI is intentionally ignored.
- **Redis TLS**: the app connects with `rediss://`. If a client rejects the
  cert, append `?ssl_cert_reqs=none` to `redis_url` in `redis.tf` (the
  network path is SG-isolated either way).

## Cost (rough, us-west-2)

~$130–150/mo: NAT gateways ~$65, ALB ~$18, 4 Fargate tasks ~$35, ElastiCache
~$11, WAF ~$10, plus pennies for Route53/ECR/logs. Supabase free tier $0.
`terraform destroy` tears it all down (the registered domain and state bucket
survive).
