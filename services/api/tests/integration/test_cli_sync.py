"""End-to-end sync CLI test: runs the real `trace-sync` binary as a
subprocess against the live stack with a freshly minted key. Pins the
CLI↔API contract that the CLI's mock-transport unit tests can't see
(response field names, dedupe semantics, verbatim error surfacing).
"""

import json
import os
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

from tests.integration.conftest import API_URL, otlp_payload

CLI_DIR = Path(__file__).resolve().parents[4] / "apps" / "cli"


@pytest.fixture
async def api_key(api: httpx.AsyncClient) -> str:
    res = await api.post("/v1/api-keys", json={"name": "cli e2e"})
    assert res.status_code == 201
    return res.json()["api_key"]


def run_cli(key: str, *paths: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "trace-sync", "sync", *map(str, paths)],
        cwd=CLI_DIR,
        env={**os.environ, "TRACE_API_URL": API_URL, "TRACE_API_KEY": key},
        capture_output=True,
        text=True,
        timeout=180,
    )


async def test_cli_sync_end_to_end(api_key: str, db, tmp_path: Path):
    good = tmp_path / "good.json"
    good.write_bytes(otlp_payload(uuid.uuid4().hex))

    # First sync: uploads, polls to terminal, reports the trace count.
    res = run_cli(api_key, good)
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"{good} → uploaded (complete, 1 trace)" in res.stdout
    assert "synced 1 · skipped 0 · failed 0" in res.stdout

    # The API inferred the source from key auth; the CLI never sent it.
    source = await db.fetchval(
        "select source from uploads where filename = $1 order by created_at desc limit 1",
        good.name,
    )
    assert source == "cli"

    # Re-sync: server-side sha dedupe, nothing uploaded, still exit 0.
    res = run_cli(api_key, good)
    assert res.returncode == 0
    assert f"{good} → already synced" in res.stdout
    assert "synced 0 · skipped 1 · failed 0" in res.stdout


async def test_cli_surfaces_ingestion_failure_verbatim(api_key: str, tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(json.dumps({"resourceSpans": [], "_m": uuid.uuid4().hex}).encode())

    res = run_cli(api_key, bad)
    assert res.returncode == 1
    assert f"{bad} → failed: Payload contains no valid spans (no spans found)." in res.stdout
    assert "synced 0 · skipped 0 · failed 1" in res.stdout


async def test_cli_bad_key_is_unrunnable(tmp_path: Path):
    f = tmp_path / "a.json"
    f.write_bytes(otlp_payload(uuid.uuid4().hex))

    res = run_cli("tmk_" + "x" * 32, f)
    assert res.returncode == 2
    assert "API key rejected" in res.stderr  # fatal errors go to stderr
