"""Shared helpers for the local-stack scripts (seed, smoke).

stdlib-only on purpose, like the other tools: runnable on a fresh clone with
plain python3. Reads the repo .env (then .env.local, then real env vars) for
the Supabase URL and service-role key.
"""

import json
import time
import urllib.error
import urllib.request
from os import environ
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    env.update(environ)
    return env


class StackError(RuntimeError):
    pass


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
    except urllib.error.URLError as err:
        raise StackError(f"cannot reach {url}: {err.reason} — is the stack running?") from err


def sign_in(env: dict[str, str], email: str, password: str) -> str:
    """Sign up (or sign in, when the user already exists) and return a JWT."""
    supabase = env.get("SUPABASE_URL", "http://127.0.0.1:55321")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise StackError("SUPABASE_SERVICE_ROLE_KEY not set (copy .env.example to .env)")
    creds = json.dumps({"email": email, "password": password}).encode()
    headers = {"apikey": key, "Content-Type": "application/json"}
    for path in ("/auth/v1/signup", "/auth/v1/token?grant_type=password"):
        status, body = _request(f"{supabase}{path}", method="POST", headers=headers, body=creds)
        if status == 200:
            return json.loads(body)["access_token"]
    raise StackError(f"auth failed for {email}: {body.decode(errors='replace')[:200]}")


class Api:
    """Minimal authenticated client for the marketplace API."""

    def __init__(self, env: dict[str, str], token: str) -> None:
        self.base = env.get("API_URL", "http://localhost:8000")
        self.token = token

    def request(
        self, method: str, path: str, *, json_body: dict | None = None
    ) -> tuple[int, dict | bytes]:
        headers = {"Authorization": f"Bearer {self.token}"}
        body = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(json_body).encode()
        status, raw = _request(f"{self.base}{path}", method=method, headers=headers, body=body)
        try:
            return status, json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, raw

    def upload(self, filename: str, data: bytes) -> tuple[int, dict]:
        boundary = "seedboundary7af3c1"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/json\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
        status, raw = _request(
            f"{self.base}/v1/uploads",
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            body=body,
        )
        return status, json.loads(raw)

    def download(self, path: str) -> bytes:
        status, raw = _request(
            f"{self.base}{path}", headers={"Authorization": f"Bearer {self.token}"}
        )
        if status != 200:
            raise StackError(f"download {path} failed with {status}")
        return raw


def wait_terminal(api: Api, upload_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = api.request("GET", f"/v1/uploads/{upload_id}")
        if status != 200:
            raise StackError(f"upload status check failed: {status} {body}")
        if body["status"] in ("complete", "failed"):
            return body
        time.sleep(0.5)
    raise StackError(f"upload {upload_id} never reached a terminal status")
