"""End-to-end smoke: the literal Stage 1 demo script (0_README.md), scripted.

Two throwaway accounts run the whole loop against the live local stack:
contributor uploads → ingests → inspects → lists; consumer searches the
marketplace → inspects → acquires → downloads byte-identical raw bytes.
Exits non-zero on the first failed step.

Usage: make smoke   (stack must be up: supabase start + docker compose up)
"""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _stack import ROOT, Api, StackError, load_env, sign_in, wait_terminal

run_id = uuid.uuid4().hex[:12]


def step(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        raise StackError(f"{label}: {detail}")
    print(f"  ok  {label}")


def main() -> int:
    env = load_env()

    # 1. Sign up (two accounts: every user can contribute and consume).
    contributor = Api(env, sign_in(env, f"smoke-c-{run_id}@example.com", "smoke-test-pw"))
    consumer = Api(env, sign_in(env, f"smoke-x-{run_id}@example.com", "smoke-test-pw"))
    step("sign up contributor + consumer", True)

    # 2. Upload a fixture (marker makes the bytes unique per run).
    payload = json.loads((ROOT / "fixtures" / "agent-session.json").read_text())
    payload["_smoke_marker"] = run_id
    data = json.dumps(payload).encode()
    status, body = contributor.upload("agent-session.json", data)
    step("upload fixture", status == 201, f"{status} {body}")
    upload_id = body["upload_id"]

    # 3. Ingestion reaches a terminal status.
    result = wait_terminal(contributor, upload_id)
    step("ingestion completes", result["status"] == "complete", str(result["error_message"]))
    trace_id = result["trace_ids"][0]

    # 4. Owner inspects: metadata and the full span tree.
    status, trace = contributor.request("GET", f"/v1/traces/{trace_id}")
    step("owner reads trace metadata", status == 200 and trace["is_owner"], f"{status}")
    status, spans = contributor.request("GET", f"/v1/traces/{trace_id}/spans")
    step(
        "owner reads span tree",
        status == 200 and spans["total"] == trace["span_count"] > 0,
        f"{status} total={spans.get('total')}",
    )

    # 5. Listing requires the ownership confirmation.
    status, body = contributor.request(
        "PATCH", f"/v1/traces/{trace_id}", json_body={"visibility": "listed"}
    )
    step(
        "listing without confirmation refused",
        status == 422 and body["error"]["code"] == "confirmation_required",
        f"{status} {body}",
    )
    tag = f"smoke-{run_id}"
    status, body = contributor.request(
        "PATCH",
        f"/v1/traces/{trace_id}",
        json_body={
            "visibility": "listed",
            "confirm_ownership": True,
            "tags": [tag],
            "description": "Smoke-test listing.",
        },
    )
    step("list with confirmation", status == 200 and body["visibility"] == "listed", f"{status}")

    # 6. Consumer searches the marketplace by keyword + filters.
    status, found = consumer.request("GET", f"/v1/traces?scope=marketplace&q={tag}")
    step(
        "marketplace search finds it",
        status == 200 and [t["trace_id"] for t in found["traces"]] == [trace_id],
        f"{status} {found}",
    )
    status, found = consumer.request(
        "GET", f"/v1/traces?scope=marketplace&q={tag}&has_errors=true"
    )
    step("filters apply (has_errors excludes it)", status == 200 and found["total"] == 0, f"{found}")

    # 7. Consumer inspects the listed trace.
    status, detail = consumer.request("GET", f"/v1/traces/{trace_id}")
    step(
        "consumer inspects listed trace",
        status == 200 and not detail["is_owner"] and not detail["can_download"],
        f"{status}",
    )
    status, spans = consumer.request("GET", f"/v1/traces/{trace_id}/spans")
    step("consumer reads span tree", status == 200 and spans["total"] > 0, f"{status}")

    # 8. Download is gated until acquisition.
    status, body = consumer.request("GET", f"/v1/traces/{trace_id}/download")
    step(
        "download gated before acquire",
        status == 403 and body["error"]["code"] == "acquisition_required",
        f"{status} {body}",
    )
    status, acq = consumer.request("POST", f"/v1/traces/{trace_id}/acquire")
    step("acquire ($0)", status == 201 and acq["price_usd"] == 0, f"{status} {acq}")
    status, again = consumer.request("POST", f"/v1/traces/{trace_id}/acquire")
    step(
        "acquire is idempotent",
        status == 200 and again["acquisition_id"] == acq["acquisition_id"],
        f"{status}",
    )
    status, library = consumer.request("GET", "/v1/traces?scope=acquired")
    step(
        "library shows the acquisition",
        status == 200 and [t["trace_id"] for t in library["traces"]] == [trace_id],
        f"{status}",
    )

    # 9. Download returns the original raw payload, byte-identical.
    downloaded = consumer.download(f"/v1/traces/{trace_id}/download")
    step("download is byte-identical", downloaded == data, f"{len(downloaded)} != {len(data)} bytes")

    print("\nsmoke passed: the full demo loop works end to end")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StackError as err:
        print(f"\nsmoke FAILED — {err}", file=sys.stderr)
        raise SystemExit(1) from None
