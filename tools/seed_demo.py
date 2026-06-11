"""Seed a full live demo for one account, on the local stack or production.

Reads the object manifest (tools/seed_demo.json) and, as the target user:

- uploads the listed fixtures through the real HTTP API and lists the
  resulting traces with tags + descriptions;
- applies the manifest's deterministic analysis labels (machine provenance;
  never overwrites a human answer) so every surface looks analyzed even
  without LLM keys;
- guarantees HIL content: open review items with verdict + routing reasons,
  plus an unread review_request digest notification;
- creates subscriptions and records first-matches, plus an unread
  subscription_match digest notification;
- signs in a demo contributor account that lists its own fixtures, which
  the target user acquires — so the Library page has content too.

Sign-in uses the admin magic-link flow, so it works for accounts that
already exist (e.g. your real production account) without touching their
password. Idempotent: re-runs reuse duplicate uploads, skip existing open
review items, unread digests, and matches, and re-apply listing metadata.

Usage:
    python3 tools/seed_demo.py user@example.com                     # local
    python3 tools/seed_demo.py user@example.com --stack production  # trace-mp.com
    python3 tools/seed_demo.py user@example.com --wipe              # wipe, then seed fresh
    python3 tools/seed_demo.py user@example.com --wipe-only         # wipe and stop

Production reads git-ignored .env.production (see the seed-demo skill to
regenerate it). Local targets whatever .env / .env.local point at.
"""

import argparse
import json
import sys
import time
from os import environ
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _stack import ROOT, Api, StackError, admin_sign_in, load_env, rest, wait_terminal

MANIFEST = Path(__file__).parent / "seed_demo.json"
PROD_ENV_FILE = ROOT / ".env.production"
PROD_API_URL = "https://trace-mp.com"

LABEL_FIELDS = ("outcome", "failure_mode", "task_category")
HUMAN_PROVENANCE = ("human", "human_confirmed")

# How long to wait for the analysis worker to write a trace_analysis row
# before creating one directly (the worker may be running real LLM calls).
ANALYSIS_WAIT_SECONDS = 120


def load_production_env() -> dict[str, str]:
    """Explicit, opt-in production targeting: .env.production wins over
    inherited shell vars so --stack production can never silently hit a
    local Supabase. load_env() deliberately ignores this file."""
    if not PROD_ENV_FILE.exists():
        raise StackError(
            ".env.production is missing — see .cursor/skills/seed-demo/SKILL.md to regenerate it"
        )
    env = dict(environ)
    for line in PROD_ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    env.setdefault("API_URL", PROD_API_URL)
    return env


def label_triplets(labels: dict) -> dict:
    triplets: dict = {}
    for field in LABEL_FIELDS:
        value = labels.get(field)
        triplets[field] = value
        triplets[f"{field}_confidence"] = labels.get(f"{field}_confidence")
        triplets[f"{field}_provenance"] = "machine" if value is not None else None
    return triplets


def apply_labels(env: dict, trace_id: str, labels: dict) -> None:
    """Write the manifest's label triplets onto trace_analysis, waiting for
    the analysis worker's row first (its delete-and-rewrite would clobber
    an earlier write). Human-provenance fields are never overwritten."""
    row = None
    deadline = time.monotonic() + ANALYSIS_WAIT_SECONDS
    while time.monotonic() < deadline:
        status, rows = rest(env, "GET", f"trace_analysis?trace_id=eq.{trace_id}&select=*")
        if status != 200:
            raise StackError(f"trace_analysis read failed: {status} {rows}")
        if rows:
            row = rows[0]
            break
        time.sleep(1)

    if row is None:
        print(f"  analysis never landed for {trace_id}; writing the row directly")
        status, body = rest(
            env,
            "POST",
            "trace_analysis",
            json_body={"trace_id": trace_id, "llm_status": "complete", **label_triplets(labels)},
        )
        if status not in (200, 201):
            raise StackError(f"trace_analysis insert failed: {status} {body}")
        return

    patch = {"llm_status": "complete", "llm_skip_reason": None}
    for field in LABEL_FIELDS:
        if row.get(f"{field}_provenance") in HUMAN_PROVENANCE:
            continue  # a human already answered; their label stands
        value = labels.get(field)
        patch[field] = value
        patch[f"{field}_confidence"] = labels.get(f"{field}_confidence")
        patch[f"{field}_provenance"] = "machine" if value is not None else None
    status, body = rest(env, "PATCH", f"trace_analysis?trace_id=eq.{trace_id}", json_body=patch)
    if status not in (200, 204):
        raise StackError(f"trace_analysis update failed: {status} {body}")


def ensure_review_item(env: dict, trace_id: str, labels: dict, reasons: list[dict]) -> bool:
    """Create an open review item unless the trace already has one (the
    partial unique index allows at most one). Returns True when created."""
    status, rows = rest(
        env, "GET", f"review_items?trace_id=eq.{trace_id}&status=eq.open&select=id"
    )
    if status != 200:
        raise StackError(f"review_items read failed: {status} {rows}")
    if rows:
        return False
    context = {
        "verdict": {
            field: labels.get(field)
            for label in LABEL_FIELDS
            for field in (label, f"{label}_confidence")
        },
        "reasons": reasons,
    }
    status, body = rest(
        env, "POST", "review_items", json_body={"trace_id": trace_id, "context": context}
    )
    if status == 409:  # raced another writer; the open item exists
        return False
    if status not in (200, 201):
        raise StackError(f"review_items insert failed: {status} {body}")
    return True


def ensure_unread_digest(env: dict, user_id: str, type_: str, key: str, payload: dict) -> bool:
    """Insert an unread digest notification unless one already occupies the
    (user, payload key) slot — mirroring the worker's upsert targets."""
    status, rows = rest(
        env,
        "GET",
        f"notifications?user_id=eq.{user_id}&type=eq.{type_}&read_at=is.null"
        f"&payload->>{key}=eq.{payload[key]}&select=id",
    )
    if status != 200:
        raise StackError(f"notifications read failed: {status} {rows}")
    if rows:
        return False
    status, body = rest(
        env,
        "POST",
        "notifications",
        json_body={"user_id": user_id, "type": type_, "payload": payload},
    )
    if status not in (200, 201):
        raise StackError(f"notifications insert failed: {status} {body}")
    return True


def wipe_user(api: Api, env: dict, user_id: str, email: str) -> None:
    """Delete the user's data: owned traces through the API (uploads rows and
    storage objects ride along when the last trace goes), leftover empty
    upload rows, subscriptions (matches cascade), acquisitions, and
    notifications. The account, allowlist entry, and API keys stay; other
    accounts' data (e.g. the demo contributor's listings) is untouched."""
    deleted = 0
    while True:
        status, body = api.request("GET", "/v1/traces?scope=mine&limit=100")
        if status != 200:
            raise StackError(f"listing traces failed: {status} {body}")
        if not body["traces"]:
            break
        for trace in body["traces"]:
            status, b = api.request("DELETE", f"/v1/traces/{trace['trace_id']}")
            if status != 204:
                raise StackError(f"deleting trace {trace['trace_id']} failed: {status} {b}")
            deleted += 1

    # Upload rows whose traces were already deleted in the UI never get
    # cleaned by the trace-delete path; drop them directly. Their storage
    # objects orphan — harmless, content-addressed.
    status, rows = rest(env, "GET", f"uploads?owner_id=eq.{user_id}&select=id")
    if status != 200:
        raise StackError(f"listing uploads failed: {status} {rows}")
    for row in rows or []:
        rest(env, "DELETE", f"uploads?id=eq.{row['id']}")

    status, body = api.request("GET", "/v1/subscriptions")
    if status != 200:
        raise StackError(f"listing subscriptions failed: {status} {body}")
    for sub in body["subscriptions"]:
        api.request("DELETE", f"/v1/subscriptions/{sub['subscription_id']}")

    # No client API for these (server-generated / append-only): service role.
    rest(env, "DELETE", f"acquisitions?consumer_id=eq.{user_id}")
    rest(env, "DELETE", f"notifications?user_id=eq.{user_id}")
    print(
        f"wiped {email}: {deleted} trace(s) plus uploads, subscriptions, "
        "acquisitions, and notifications"
    )


def seed_upload(api: Api, env: dict, user_id: str, entry: dict) -> tuple[str, list[str]]:
    """Upload one fixture, list + label its traces, and seed its review
    content. Returns (upload_id, trace_ids)."""
    name = entry["fixture"]
    data = (ROOT / "fixtures" / name).read_bytes()
    status, body = api.upload(name, data)
    if status == 201:
        upload_id = body["upload_id"]
    elif status == 409 and body["error"]["code"] == "duplicate_upload":
        upload_id = body["error"]["details"]["upload_id"]
    else:
        raise StackError(f"upload {name} failed: {status} {body}")

    result = wait_terminal(api, upload_id)
    if result["status"] != "complete":
        raise StackError(f"ingest {name} failed: {result['error_message']}")
    trace_ids = result["trace_ids"]
    if not trace_ids:
        # Duplicate upload whose traces were deleted in the UI; only an
        # operator re-ingest brings them back.
        print(f"  {name}: upload exists but its traces were deleted — recover with: "
              f"make requeue UPLOAD={upload_id}")

    for trace_id in trace_ids:
        status, body = api.request(
            "PATCH",
            f"/v1/traces/{trace_id}",
            json_body={
                "visibility": "listed",
                "confirm_ownership": True,
                "tags": entry["tags"],
                "description": entry["description"],
            },
        )
        if status != 200:
            raise StackError(f"listing {name} trace failed: {status} {body}")
        apply_labels(env, trace_id, entry["analysis"])

    new_items = 0
    if entry.get("review"):
        for trace_id in trace_ids:
            if ensure_review_item(env, trace_id, entry["analysis"], entry["review"]["reasons"]):
                new_items += 1
        if new_items:
            ensure_unread_digest(
                env,
                user_id,
                "review_request",
                "upload_id",
                {"upload_id": upload_id, "filename": name, "item_count": new_items},
            )
    print(
        f"seeded {name}: {len(trace_ids)} listed+labeled trace(s)"
        + (f", {new_items} review item(s)" if new_items else "")
    )
    return upload_id, trace_ids


def seed_library(api: Api, env: dict, contributor: dict) -> None:
    """A second account (the demo contributor) lists a few traces, and the
    target user acquires them — so the Library page has content and the
    marketplace looks multi-user. `api` is the target user's client."""
    c_token, c_user_id = admin_sign_in(env, contributor["email"])
    c_api = Api(env, c_token)
    acquired = 0
    for entry in contributor["uploads"]:
        _, trace_ids = seed_upload(c_api, env, c_user_id, entry)
        for trace_id in trace_ids:
            status, body = api.request("POST", f"/v1/traces/{trace_id}/acquire")
            if status in (200, 201):
                acquired += 1
            elif not (status == 409 and body["error"]["code"] == "own_trace"):
                raise StackError(f"acquiring trace {trace_id} failed: {status} {body}")
    print(f"acquired {acquired} contributor trace(s) into the library")


def seed_subscription(
    api: Api, env: dict, user_id: str, sub: dict, fixture_traces: dict[str, list[str]]
) -> None:
    status, body = api.request("GET", "/v1/subscriptions")
    if status != 200:
        raise StackError(f"listing subscriptions failed: {status} {body}")
    existing = {s["name"]: s for s in body["subscriptions"]}
    if sub["name"] in existing:
        sub_id = existing[sub["name"]]["subscription_id"]
    else:
        status, body = api.request(
            "POST", "/v1/subscriptions", json_body={"name": sub["name"], "query": sub["query"]}
        )
        if status != 201:
            raise StackError(f"creating subscription {sub['name']} failed: {status} {body}")
        sub_id = body["subscription_id"]

    new_matches: list[str] = []
    for fixture in sub.get("matches", []):
        for trace_id in fixture_traces.get(fixture, []):
            status, rows = rest(
                env,
                "GET",
                f"subscription_matches?subscription_id=eq.{sub_id}&trace_id=eq.{trace_id}&select=id",
            )
            if status != 200:
                raise StackError(f"subscription_matches read failed: {status} {rows}")
            if rows:
                continue
            status, body = rest(
                env,
                "POST",
                "subscription_matches",
                json_body={"subscription_id": sub_id, "trace_id": trace_id},
            )
            if status in (200, 201):
                new_matches.append(trace_id)
            elif status != 409:  # 409 = the worker matched it first
                raise StackError(f"subscription_matches insert failed: {status} {body}")

    if new_matches:
        # Mirror the worker's payload: trace_id only when a single match
        # (links to the trace; a digest links to the feed).
        payload = {"subscription_id": sub_id, "name": sub["name"], "match_count": len(new_matches)}
        if len(new_matches) == 1:
            payload["trace_id"] = new_matches[0]
        ensure_unread_digest(env, user_id, "subscription_match", "subscription_id", payload)
    print(f"seeded subscription {sub['name']!r}: {len(new_matches)} new match(es)")


def seed_demo(email: str, stack: str, *, wipe: bool = False, wipe_only: bool = False) -> int:
    manifest = json.loads(MANIFEST.read_text())
    env = load_production_env() if stack == "production" else load_env()
    action = "wiping" if wipe_only else "seeding demo for"
    print(f"{action} {email} on {stack} ({env.get('API_URL', 'http://localhost:8000')})")

    token, user_id = admin_sign_in(env, email)
    api = Api(env, token)

    if wipe or wipe_only:
        wipe_user(api, env, user_id, email)
        if wipe_only:
            return 0

    fixture_traces: dict[str, list[str]] = {}
    for entry in manifest["uploads"]:
        _, trace_ids = seed_upload(api, env, user_id, entry)
        fixture_traces[entry["fixture"]] = trace_ids

    contributor = manifest["contributor"]
    if contributor["email"].lower() == email.lower():
        print("target email is the demo contributor; skipping library seeding")
    else:
        seed_library(api, env, contributor)

    for sub in manifest["subscriptions"]:
        seed_subscription(api, env, user_id, sub, fixture_traces)

    print(f"\ndemo seeded — sign in as {email} (allowlisted) and open the app")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email", help="account to seed (created if missing)")
    parser.add_argument(
        "--stack",
        choices=("local", "production"),
        default="local",
        help="local (.env, default) or production (.env.production + trace-mp.com)",
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="delete the account's existing data first, then seed fresh",
    )
    parser.add_argument(
        "--wipe-only",
        action="store_true",
        help="delete the account's existing data and stop (no seeding)",
    )
    args = parser.parse_args()
    if "@" not in args.email:
        parser.error("email must contain @")
    try:
        return seed_demo(args.email, args.stack, wipe=args.wipe, wipe_only=args.wipe_only)
    except StackError as err:
        print(f"seed-demo failed: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
