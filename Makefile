# Operator commands. See README.md for the full local-run guide.

# Requeue a dead-lettered upload: make requeue UPLOAD=<upload_id>
requeue:
ifndef UPLOAD
	$(error usage: make requeue UPLOAD=<upload_id>)
endif
	cd services/api && uv run python -m app.cli.requeue $(UPLOAD)

.PHONY: requeue
