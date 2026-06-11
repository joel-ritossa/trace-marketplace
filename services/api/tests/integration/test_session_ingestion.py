"""Native session ingestion end-to-end (8_session-ingestion.md): raw agent
session JSONL uploads through the real stack into per-turn traces; unsupported
schemas reject at POST; detected-but-empty sessions fail ingestion verbatim.
"""

import asyncio
import json
import uuid
from pathlib import Path

import httpx

from tests.integration.conftest import otlp_payload, signup_token

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _marked(name: str) -> bytes:
    """Fixture bytes made unique per run (a trailing non-JSON comment line is
    skipped by the tolerant JSONL parser) so per-user dedupe never collides."""
    return fixture_bytes(name) + f"# {uuid.uuid4().hex}\n".encode()


async def _upload(api: httpx.AsyncClient, filename: str, data: bytes) -> httpx.Response:
    return await api.post("/v1/uploads", files={"file": (filename, data, "application/json")})


async def _await_terminal(api: httpx.AsyncClient, upload_id: str) -> dict:
    for _ in range(60):
        res = await api.get(f"/v1/uploads/{upload_id}")
        assert res.status_code == 200
        body = res.json()
        if body["status"] in ("complete", "failed"):
            return body
        await asyncio.sleep(1)
    raise AssertionError(f"upload {upload_id} never reached a terminal state")


async def test_codex_jsonl_lands_as_per_turn_traces(api: httpx.AsyncClient, db):
    res = await _upload(api, "rollout-demo.jsonl", _marked("codex-session.jsonl"))
    assert res.status_code == 201, res.text
    body = await _await_terminal(api, res.json()["upload_id"])
    assert body["status"] == "complete"
    assert len(body["trace_ids"]) == 2  # one trace per turn

    rows = await db.fetch(
        "select name, source_format, span_count from traces where id = any($1::uuid[]) "
        "order by started_at",
        body["trace_ids"],
    )
    assert [r["name"] for r in rows] == [
        "codex: Add a healthcheck endpoint",
        "codex: Now add a test for it",
    ]
    assert all(r["source_format"] == "codex_jsonl" for r in rows)
    assert all(r["span_count"] == 3 for r in rows)


async def test_claude_jsonl_lands_as_per_turn_traces(api: httpx.AsyncClient, db):
    res = await _upload(api, "claude-transcript.jsonl", _marked("claude-session.jsonl"))
    assert res.status_code == 201, res.text
    body = await _await_terminal(api, res.json()["upload_id"])
    assert body["status"] == "complete"
    assert len(body["trace_ids"]) == 2  # one trace per turn

    rows = await db.fetch(
        "select name, source_format, model, total_tokens from traces "
        "where id = any($1::uuid[]) order by started_at",
        body["trace_ids"],
    )
    assert [r["name"] for r in rows] == [
        "claude: Rename the config module",
        "claude: Update the imports too",
    ]
    # The timestamped branch of the shared anthropic parser: real clocks,
    # model ids, and usage rollups — the bits Cursor transcripts lack.
    assert all(r["source_format"] == "anthropic_jsonl" for r in rows)
    assert all(r["model"] == "claude-fable-5" for r in rows)
    assert rows[0]["total_tokens"] == 120 + 45 + 150 + 20


async def test_cursor_jsonl_ingests_clockless(api: httpx.AsyncClient, db):
    res = await _upload(api, "transcript.jsonl", _marked("cursor-session.jsonl"))
    assert res.status_code == 201, res.text
    body = await _await_terminal(api, res.json()["upload_id"])
    assert body["status"] == "complete"
    assert len(body["trace_ids"]) == 1

    name = await db.fetchval("select name from traces where id = $1::uuid", body["trace_ids"][0])
    assert name == "cursor: Fix the flaky test"


async def test_grown_session_resync_is_idempotent(api: httpx.AsyncClient, db):
    """Owner-scoped trace identity (6_architecture.md A6): a re-sync of a
    session that grew adopts the existing turn traces into the new upload
    and appends only the new turn — no duplicates, stable trace ids."""
    # Unique session id so identity can't collide across runs of this test.
    v1 = fixture_bytes("codex-session.jsonl").replace(b"sess-codex-demo", uuid.uuid4().hex.encode())
    res = await _upload(api, "rollout-grow.jsonl", v1)
    assert res.status_code == 201, res.text
    first_upload = res.json()["upload_id"]
    first = await _await_terminal(api, first_upload)
    assert first["status"] == "complete"
    assert len(first["trace_ids"]) == 2

    # The session grows by one turn; the file re-syncs as a new upload.
    extra_turn = (
        b'{"timestamp":"2026-01-15T10:02:00Z","type":"event_msg",'
        b'"payload":{"type":"user_message","message":"Also update the docs"}}\n'
        b'{"timestamp":"2026-01-15T10:02:05Z","type":"response_item",'
        b'"payload":{"type":"message","role":"assistant",'
        b'"content":[{"type":"output_text","text":"Docs updated."}]}}\n'
    )
    res = await _upload(api, "rollout-grow.jsonl", v1 + extra_turn)
    assert res.status_code == 201, res.text
    second = await _await_terminal(api, res.json()["upload_id"])
    assert second["status"] == "complete"

    # The new upload owns all three turns; the first two kept their ids.
    assert len(second["trace_ids"]) == 3
    assert set(first["trace_ids"]) <= set(second["trace_ids"])

    # The superseded upload owns nothing; the owner has no duplicates.
    res = await api.get(f"/v1/uploads/{first_upload}")
    assert res.json()["trace_ids"] == []
    owner_total = await db.fetchval(
        "select count(*) from traces where id = any($1::uuid[]) or upload_id = $2::uuid",
        second["trace_ids"],
        first_upload,
    )
    assert owner_total == 3


async def test_byte_identical_session_resync_blocks_409(api: httpx.AsyncClient):
    """Identity has two layers: byte-identical re-uploads never even create
    an upload (per-user sha dedupe blocks at POST); only changed bytes reach
    the adoption path."""
    data = _marked("codex-session.jsonl")
    first = await _upload(api, "rollout.jsonl", data)
    assert first.status_code == 201, first.text

    again = await _upload(api, "rollout.jsonl", data)
    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "duplicate_upload"
    assert error["details"]["upload_id"] == first.json()["upload_id"]


async def test_same_session_different_owners_stay_isolated(api: httpx.AsyncClient, db):
    """Identity is owner-scoped, not global: two users uploading the same
    session must each get their own traces — adoption never crosses owners."""
    data = _marked("codex-session.jsonl")  # same bytes, same source trace ids
    mine = await _upload(api, "rollout.jsonl", data)
    assert mine.status_code == 201, mine.text
    mine_body = await _await_terminal(api, mine.json()["upload_id"])
    assert len(mine_body["trace_ids"]) == 2

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=api.base_url, headers={"Authorization": f"Bearer {other_token}"}, timeout=30.0
    ) as other:
        theirs = await _upload(other, "rollout.jsonl", data)
        assert theirs.status_code == 201, theirs.text
        theirs_body = await _await_terminal(other, theirs.json()["upload_id"])
    assert len(theirs_body["trace_ids"]) == 2

    # Same source ids, two owners, four distinct rows — mine still mine.
    assert set(mine_body["trace_ids"]).isdisjoint(theirs_body["trace_ids"])
    still_mine = await db.fetchval(
        "select count(*) from traces where id = any($1::uuid[]) and upload_id = $2::uuid",
        mine_body["trace_ids"],
        mine.json()["upload_id"],
    )
    assert still_mine == 2


async def test_owner_state_survives_resync(api: httpx.AsyncClient):
    """The point of stable identity: labels and curation put on a turn trace
    must survive the session growing and re-syncing."""
    v1 = fixture_bytes("codex-session.jsonl").replace(b"sess-codex-demo", uuid.uuid4().hex.encode())
    res = await _upload(api, "rollout-state.jsonl", v1)
    assert res.status_code == 201, res.text
    first = await _await_terminal(api, res.json()["upload_id"])
    turn_id = first["trace_ids"][0]

    res = await api.patch(
        f"/v1/traces/{turn_id}",
        json={"tags": ["keeper"], "description": "good repro of the bug"},
    )
    assert res.status_code == 200, res.text

    res = await _upload(api, "rollout-state.jsonl", v1 + b'{"type":"event_msg"}\n')
    assert res.status_code == 201, res.text
    second = await _await_terminal(api, res.json()["upload_id"])
    assert second["status"] == "complete"
    assert turn_id in second["trace_ids"]  # same row, adopted

    res = await api.get(f"/v1/traces/{turn_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["tags"] == ["keeper"]
    assert body["description"] == "good repro of the bug"


async def test_otlp_reupload_same_trace_id_adopts(api: httpx.AsyncClient, db):
    """The identity rule is universal, not a session special case: an OTLP
    re-upload carrying the same trace id updates that trace in place."""
    first = await _upload(api, "export.json", otlp_payload(uuid.uuid4().hex))
    assert first.status_code == 201, first.text
    first_body = await _await_terminal(api, first.json()["upload_id"])
    assert len(first_body["trace_ids"]) == 1

    # Different bytes (new marker), same traceId inside the payload.
    second = await _upload(api, "export.json", otlp_payload(uuid.uuid4().hex))
    assert second.status_code == 201, second.text
    second_body = await _await_terminal(api, second.json()["upload_id"])
    assert second_body["status"] == "complete"
    assert second_body["trace_ids"] == first_body["trace_ids"]  # adopted, not duplicated

    owner_rows = await db.fetchval(
        "select count(*) from traces where id = $1::uuid", first_body["trace_ids"][0]
    )
    assert owner_rows == 1
    res = await api.get(f"/v1/uploads/{first.json()['upload_id']}")
    assert res.json()["trace_ids"] == []  # superseded upload owns nothing


async def test_unsupported_schema_rejects_at_post(api: httpx.AsyncClient):
    res = await _upload(api, "app-log.jsonl", _marked("unsupported-log.jsonl"))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "unsupported_format"


async def test_detected_but_empty_session_fails_verbatim(api: httpx.AsyncClient):
    meta_only = (
        json.dumps({"type": "session_meta", "payload": {"id": uuid.uuid4().hex, "cwd": "/"}}) + "\n"
    ).encode()
    res = await _upload(api, "rollout-empty.jsonl", meta_only)
    assert res.status_code == 201, res.text  # detection passes…
    body = await _await_terminal(api, res.json()["upload_id"])
    assert body["status"] == "failed"  # …conversion rejects, reason verbatim
    assert "no convertible turns" in body["error_message"]
