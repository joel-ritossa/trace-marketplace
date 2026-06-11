# Operator commands. See README.md for the full local-run guide.

# Requeue a dead-lettered upload: make requeue UPLOAD=<upload_id>
requeue:
ifndef UPLOAD
	$(error usage: make requeue UPLOAD=<upload_id>)
endif
	cd services/api && uv run python -m app.cli.requeue $(UPLOAD)

.PHONY: requeue

# Pull real benchmark traces (Exgentic/agent-llm-traces, CDLA-Permissive-2.0)
# into git-ignored devdata/ as uploadable OTLP JSON.
# Options: make dev-dataset ARGS="--count 10 --min-spans 50"
dev-dataset:
	python3 tools/exgentic_to_otlp.py $(ARGS)

.PHONY: dev-dataset

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
