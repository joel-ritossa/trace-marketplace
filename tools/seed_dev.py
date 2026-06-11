"""Seed the local stack with real benchmark traces through the sync CLI.

The real-data counterpart to seed.py (which uploads the synthetic fixtures):
converts Exgentic/agent-llm-traces sessions into git-ignored devdata/ if none
exist, mints a `seed` API key for the demo contributor, uploads every
converted file through the actual `trace-sync` CLI (dogfooding the machine
door end to end), waits for ingestion, and lists the traces tagged by
harness/benchmark. Idempotent: server-side sha256 dedupe makes re-uploads
skips, and listing metadata is re-applied.

The minted key is printed at the end and stays valid — reuse it as
TRACE_API_KEY for manual CLI runs. Re-running rotates it (old `seed` keys
are revoked).

Usage: make seed-dev   (stack must be up: supabase start + docker compose up)
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _stack import ROOT, Api, StackError, load_env, sign_in, wait_terminal

from seed import DEMO_EMAIL, DEMO_PASSWORD

DEVDATA = ROOT / "devdata"
# Converter defaults: enough sessions for a lively UI, strided for variety,
# big enough to be interesting.
CONVERT_ARGS = ["--count", "24", "--spread", "--min-spans", "10"]
SEED_KEY_NAME = "seed"


def converted_files() -> list[Path]:
    # The converter names files <harness>-<benchmark>-<session>-<N>spans.json;
    # this skips the hand-made stress files (large-trace.json, over-cap.json).
    return sorted(DEVDATA.glob("*spans.json"))


def ensure_devdata() -> list[Path]:
    files = converted_files()
    if files:
        return files
    print(f"devdata/ has no converted sessions — fetching ({' '.join(CONVERT_ARGS)})")
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "exgentic_to_otlp.py"), *CONVERT_ARGS],
        check=True,
        cwd=ROOT,
    )
    files = converted_files()
    if not files:
        raise StackError("converter produced no files")
    return files


def rotate_seed_key(api: Api) -> str:
    """Revoke previous `seed` keys, mint a fresh one, return its plaintext."""
    status, body = api.request("GET", "/v1/api-keys")
    if status != 200:
        raise StackError(f"listing api keys failed: {status} {body}")
    for key in body["api_keys"]:
        if key["name"] == SEED_KEY_NAME and key["revoked_at"] is None:
            api.request("DELETE", f"/v1/api-keys/{key['api_key_id']}")
    status, body = api.request("POST", "/v1/api-keys", json_body={"name": SEED_KEY_NAME})
    if status != 201:
        raise StackError(f"minting api key failed: {status} {body}")
    return body["api_key"]


def run_trace_sync(files: list[Path], api_url: str, api_key: str) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(ROOT / "apps" / "cli"),
            "trace-sync",
            "sync",
            *map(str, files),
            "--api-url",
            api_url,
            "--api-key",
            api_key,
        ],
        cwd=ROOT,
    )
    # Exit 1 = some files failed (printed per file); keep going so the rest
    # still get listed. Exit 2 = unrunnable (bad key/url) — nothing uploaded.
    if result.returncode == 2:
        raise StackError("trace-sync could not run (bad API key or URL?)")


def uploads_by_filename(api: Api) -> dict[str, dict]:
    """Newest upload per filename for the demo account."""
    by_name: dict[str, dict] = {}
    offset = 0
    while True:
        status, body = api.request("GET", f"/v1/uploads?limit=100&offset={offset}")
        if status != 200:
            raise StackError(f"listing uploads failed: {status} {body}")
        for upload in body["uploads"]:
            by_name.setdefault(upload["filename"], upload)  # list is newest-first
        offset += 100
        if offset >= body["total"]:
            return by_name


def session_labels(path: Path) -> tuple[str, str]:
    """(harness, benchmark) from the converted file's synthesized root span
    attributes — set by the converter, sturdier than parsing the filename."""
    payload = json.loads(path.read_text())
    for resource in payload["resourceSpans"]:
        for scope in resource["scopeSpans"]:
            for span in scope["spans"]:
                attrs = {a["key"]: a["value"].get("stringValue") for a in span["attributes"]}
                if "exgentic.benchmark" in attrs:
                    return attrs.get("gen_ai.agent.name", "agent"), attrs["exgentic.benchmark"]
    return "agent", "benchmark"


def seed_dev() -> int:
    env = load_env()
    files = ensure_devdata()
    api = Api(env, sign_in(env, DEMO_EMAIL, DEMO_PASSWORD))
    api_key = rotate_seed_key(api)

    # flush so the line lands before the subprocess's own output when piped
    print(f"syncing {len(files)} converted session(s) through trace-sync", flush=True)
    run_trace_sync(files, api.base, api_key)

    uploads = uploads_by_filename(api)
    listed = 0
    for path in files:
        upload = uploads.get(path.name)
        if upload is None:
            print(f"{path.name}: no upload found, skipping listing", file=sys.stderr)
            continue
        result = wait_terminal(api, upload["upload_id"])
        if result["status"] != "complete":
            print(f"{path.name}: ingest failed ({result['error_message']})", file=sys.stderr)
            continue
        harness, benchmark = session_labels(path)
        for trace_id in result["trace_ids"]:
            status, body = api.request(
                "PATCH",
                f"/v1/traces/{trace_id}",
                json_body={
                    "visibility": "listed",
                    "confirm_ownership": True,
                    "tags": [harness, benchmark, "benchmark-run"],
                    "description": (
                        f"Real {harness} agent session on the {benchmark} benchmark, from "
                        "Exgentic/agent-llm-traces (CDLA-Permissive-2.0)."
                    ),
                },
            )
            if status != 200:
                raise StackError(f"listing {path.name} trace failed: {status} {body}")
            listed += 1

    print(f"\nseeded {listed} listed trace(s) from {len(files)} session file(s)")
    print(f"demo contributor: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"CLI key (valid until the next seed-dev run): TRACE_API_KEY={api_key}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(seed_dev())
    except StackError as err:
        print(f"seed-dev failed: {err}", file=sys.stderr)
        raise SystemExit(1) from None
