# Operator commands. See README.md for the full local-run guide.

# Requeue dead-lettered work: make requeue UPLOAD=<upload_id> (re-ingest;
# also re-ingests a complete upload) | make requeue TRACE=<trace_id>
# (re-run analysis).
requeue:
ifdef UPLOAD
	cd services/api && uv run python -m app.cli.requeue upload $(UPLOAD)
else ifdef TRACE
	cd services/api && uv run python -m app.cli.requeue trace $(TRACE)
else
	$(error usage: make requeue UPLOAD=<upload_id> | make requeue TRACE=<trace_id>)
endif

.PHONY: requeue

# Allowlist an email (or whole domain) for sign-up/sign-in:
#   make allow EMAIL=user@example.com | make allow EMAIL=@example.com
# Targets the stack in .env; export SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY
# to target a hosted project instead.
allow:
ifndef EMAIL
	$(error usage: make allow EMAIL=<email>)
endif
	cd tools && python3 allow_email.py $(EMAIL)

.PHONY: allow

# Pull real benchmark traces (Exgentic/agent-llm-traces, CDLA-Permissive-2.0)
# into git-ignored devdata/ as uploadable OTLP JSON.
# Options: make dev-dataset ARGS="--count 10 --min-spans 50"
dev-dataset:
	python3 tools/exgentic_to_otlp.py $(ARGS)

.PHONY: dev-dataset

# Symlink your local Codex / Claude Code / Cursor session logs into
# git-ignored devdata/sessions-src/ so trace-sync can upload them raw —
# the server detects the schema and converts per turn (8_session-ingestion.md):
#   TRACE_API_KEY=tmk_… trace-sync sync devdata/sessions-src --since-hours 24
link-sessions:
	tools/link_sessions.sh

.PHONY: link-sessions

# Populate the marketplace: fixtures uploaded + listed by a demo contributor.
seed:
	python3 tools/seed.py

# Same, with real benchmark traces: fetch/convert Exgentic sessions into
# devdata/ (if empty), upload them through the trace-sync CLI, list them.
seed-dev:
	python3 tools/seed_dev.py

# Seed a full live demo for one account (listed+labeled traces, review
# queue, notifications, subscriptions with matches). WIPE=1 deletes the
# account's existing data first (clean re-seed):
#   make seed-demo EMAIL=user@example.com [STACK=production] [WIPE=1]
seed-demo:
ifndef EMAIL
	$(error usage: make seed-demo EMAIL=<email> [STACK=production] [WIPE=1])
endif
	python3 tools/seed_demo.py $(EMAIL) --stack $(or $(STACK),local) $(if $(WIPE),--wipe)

# Wipe one account's data (traces, uploads, subscriptions, acquisitions,
# notifications) without re-seeding; the account itself stays:
#   make wipe-demo EMAIL=user@example.com [STACK=production]
wipe-demo:
ifndef EMAIL
	$(error usage: make wipe-demo EMAIL=<email> [STACK=production])
endif
	python3 tools/seed_demo.py $(EMAIL) --stack $(or $(STACK),local) --wipe-only

# Run the full Stage 1 demo script end to end against the live stack.
smoke:
	python3 tools/smoke.py

.PHONY: seed seed-dev seed-demo wipe-demo smoke
