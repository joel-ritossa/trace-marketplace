"""Seed the local stack with the committed fixtures as a demo contributor.

Creates (or reuses) a demo account, uploads each fixture through the real
HTTP API, waits for ingestion, and lists the resulting traces with tags and
descriptions — so a fresh clone has a browsable marketplace. Idempotent:
re-runs reuse the duplicate-upload 409 and re-apply the listing metadata.

Usage: make seed   (stack must be up: supabase start + docker compose up)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _stack import ROOT, Api, StackError, load_env, sign_in, wait_terminal

DEMO_EMAIL = "demo-contributor@example.com"
DEMO_PASSWORD = "demo-trace-marketplace"

# Fixture -> (tags, description) shown on the marketplace listing.
LISTINGS = {
    "agent-session": (
        ["weather", "tool-use", "demo"],
        "Synthetic weather-assistant session: agent → LLM → retriever → "
        "embedding → tool chain, with token counts on every model call.",
    ),
    "failure-trace": (
        ["failure", "timeout", "demo"],
        "Synthetic failing run: a web_search tool call times out and the "
        "exception event is preserved (TimeoutError).",
    ),
    "minimal": (
        ["minimal", "demo"],
        "Single-span minimal OTLP trace — the smallest valid payload.",
    ),
    "malformed-spans": (
        ["partial-parse", "demo"],
        "Mixed-quality payload: valid spans ingest, malformed ones are "
        "skipped and counted in parse warnings.",
    ),
}


def seed() -> int:
    env = load_env()
    api = Api(env, sign_in(env, DEMO_EMAIL, DEMO_PASSWORD))

    for name, (tags, description) in LISTINGS.items():
        data = (ROOT / "fixtures" / f"{name}.json").read_bytes()
        status, body = api.upload(f"{name}.json", data)
        if status == 201:
            upload_id = body["upload_id"]
        elif status == 409 and body["error"]["code"] == "duplicate_upload":
            upload_id = body["error"]["details"]["upload_id"]
        else:
            raise StackError(f"upload {name} failed: {status} {body}")

        result = wait_terminal(api, upload_id)
        if result["status"] != "complete":
            raise StackError(f"ingest {name} failed: {result['error_message']}")

        for trace_id in result["trace_ids"]:
            status, body = api.request(
                "PATCH",
                f"/v1/traces/{trace_id}",
                json_body={
                    "visibility": "listed",
                    "confirm_ownership": True,
                    "tags": tags,
                    "description": description,
                },
            )
            if status != 200:
                raise StackError(f"listing {name} trace failed: {status} {body}")
        print(f"seeded {name}: {len(result['trace_ids'])} listed trace(s)")

    print(f"\nmarketplace seeded — demo contributor: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(seed())
    except StackError as err:
        print(f"seed failed: {err}", file=sys.stderr)
        raise SystemExit(1) from None
