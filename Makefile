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

# Convert your own local Codex / Claude Code / Cursor sessions (past 24 h
# by default) into uploadable OTLP JSON under git-ignored
# devdata/agent-sessions/. Sources are read via symlinks the script
# maintains in devdata/sessions-src/, so each run picks up the latest
# sessions.
# Options: make my-sessions ARGS="--source cursor --hours 0 --count 20"
my-sessions:
	tools/my_sessions.sh $(ARGS)

.PHONY: my-sessions

# Populate the marketplace: fixtures uploaded + listed by a demo contributor.
seed:
	python3 tools/seed.py

# Same, with real benchmark traces: fetch/convert Exgentic sessions into
# devdata/ (if empty), upload them through the trace-sync CLI, list them.
seed-dev:
	python3 tools/seed_dev.py

# Run the full Stage 1 demo script end to end against the live stack.
smoke:
	python3 tools/smoke.py

.PHONY: seed seed-dev smoke
