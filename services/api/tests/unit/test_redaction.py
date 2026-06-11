"""Redaction module behavior (7_redaction.md): recognizers, false-positive
guards, deterministic placeholders, artifact/spans parity."""

import json
import re
from pathlib import Path

import pytest

from app.redaction import (
    OFFLINE_SALT,
    scrub_otlp_payload,
    scrub_text,
    scrub_tree,
)

FIXTURES_DIR = Path(__file__).parents[4] / "fixtures"

SALT = "unit-test-salt"

PLACEHOLDER = re.compile(r"<([A-Z_]+)_[0-9a-f]{8}>")


def kinds(text: str) -> list[str]:
    return PLACEHOLDER.findall(text)


class TestRecognizers:
    @pytest.mark.parametrize(
        ("text", "key", "kind"),
        [
            ("reach me at alice@example.com", None, "EMAIL"),
            ("call +1 415 555 2671", None, "PHONE"),
            ("call (212) 867-5309", None, "PHONE"),
            ("card 4111 1111 1111 1111", None, "CREDIT_CARD"),
            ("card 4111111111111111", None, "CREDIT_CARD"),
            ("ssn 219-09-9999", None, "SSN"),
            ("from 8.8.8.8", None, "IP"),
            ("AKIAIOSFODNN7EXAMPLE", "aws_key", "API_KEY"),
            ("hunter2secret", "password", "SECRET"),
            (
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
                "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
                "token",
                "JWT",
            ),
        ],
    )
    def test_positive(self, text: str, key: str | None, kind: str) -> None:
        out, counts = scrub_text(text, SALT, key)
        assert kinds(out) == [kind]
        assert counts == {kind: 1}

    def test_private_key_block_fully_masked(self) -> None:
        block = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Z3VS5JJcds3xfn\n"
            "-----END RSA PRIVATE KEY-----"
        )
        out, counts = scrub_text(f"key: {block}", SALT, "tool.arguments")
        assert kinds(out) == ["PRIVATE_KEY"]
        assert "BEGIN" not in out and "MIIEow" not in out
        assert counts == {"PRIVATE_KEY": 1}

    @pytest.mark.parametrize(
        ("text", "key"),
        [
            # id-shaped high entropy: span/trace ids, sha256, UUIDs
            ("4bf92f3577b34da6a3ce929d0e0e4736", "trace_id"),
            ("b7ad6b7169203331", "span_id"),
            ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "sha"),
            ("550e8400-e29b-41d4-a716-446655440000", "request_id"),
            # unix-nanos / unix-millis digit runs are not credit cards
            ("1768471400000000000", "startTimeUnixNano"),
            ("1768471400000", "timestamp_ms"),
            # non-global IPs stay readable
            ("10.0.0.12 and 127.0.0.1 and 192.168.1.5", None),
            # ordinary prose and URLs
            ("retrieve the weather for tomorrow", "gen_ai.prompt"),
            ("https://api.example.com/v1/users?page=2", "http.url"),
            ("2026-01-15T09:30:00+00:00", "timestamp"),
        ],
    )
    def test_negative(self, text: str, key: str | None) -> None:
        out, counts = scrub_text(text, SALT, key)
        assert out == text
        assert not counts


class TestJsonBlobRecursion:
    """Key context inside stringified JSON (message blobs) still fires."""

    def test_keyword_context_inside_blob(self) -> None:
        blob = '[{"role": "user", "content": "hi", "api_key": "q7Rt9xK2mNp4LwZ8"}]'
        out, counts = scrub_text(blob, SALT, "gen_ai.input.messages")
        assert "q7Rt9xK2mNp4LwZ8" not in out
        assert counts["SECRET"] == 1

    def test_keyword_inline_in_blob_prose(self) -> None:
        # The keyword sits inside the message text, not as a JSON field.
        blob = '[{"role": "user", "content": "use api_key: \\"q7Rt9xK2mNp4LwZ8\\" for auth"}]'
        out, counts = scrub_text(blob, SALT, "gen_ai.input.messages")
        assert "q7Rt9xK2mNp4LwZ8" not in out
        assert counts["SECRET"] == 1

    def test_formatting_preserved_not_reserialized(self) -> None:
        blob = '{ "password":   "hunter2secret" ,\n  "note": "keep spacing" }'
        out, _ = scrub_text(blob, SALT, "payload")
        assert "hunter2secret" not in out
        # Only the secret substring is replaced; the odd spacing survives.
        assert out.startswith('{ "password":   "<SECRET_')
        assert out.endswith('"note": "keep spacing" }')

    def test_nested_blob_within_blob(self) -> None:
        inner = json.dumps({"secret": "deepDarkValue99"})
        outer = json.dumps([{"role": "tool", "content": inner}])
        out, counts = scrub_text(outer, SALT, "gen_ai.output.messages")
        assert "deepDarkValue99" not in out
        assert counts["SECRET"] == 1

    def test_non_json_and_clean_json_untouched(self) -> None:
        for text in (
            "just prose that starts with { sort of",
            '{"role": "user", "content": "what is the weather in Paris?"}',
        ):
            out, counts = scrub_text(text, SALT, "gen_ai.input.messages")
            assert out == text
            assert not counts


class TestDeterminism:
    def test_same_value_same_salt_same_placeholder(self) -> None:
        a, _ = scrub_text("alice@example.com", SALT)
        b, _ = scrub_text("write to alice@example.com today", SALT)
        assert a in b  # same placeholder embedded in the longer text

    def test_different_salt_different_placeholder(self) -> None:
        a, _ = scrub_text("alice@example.com", SALT)
        b, _ = scrub_text("alice@example.com", "other-salt")
        assert a != b
        assert kinds(a) == kinds(b) == ["EMAIL"]

    def test_scrub_is_idempotent_on_output(self) -> None:
        out, _ = scrub_text("alice@example.com called +1 415 555 2671", SALT)
        again, counts = scrub_text(out, SALT)
        assert again == out
        assert not counts


class TestTree:
    def test_values_scrubbed_keys_untouched(self) -> None:
        tree = {
            "user.email": "alice@example.com",
            "nested": {"password": "hunter2secret"},
            "list": ["bob@example.com", 42, True, None],
        }
        out, counts = scrub_tree(tree, SALT)
        assert set(out) == set(tree)
        assert kinds(out["user.email"]) == ["EMAIL"]
        assert kinds(out["nested"]["password"]) == ["SECRET"]
        assert kinds(out["list"][0]) == ["EMAIL"]
        assert out["list"][1:] == [42, True, None]
        assert counts["EMAIL"] == 2


class TestArtifact:
    def test_negative_fixture_is_untouched(self) -> None:
        payload = json.loads((FIXTURES_DIR / "redaction-negative.json").read_text())
        out, counts = scrub_otlp_payload(payload, SALT)
        assert out == payload
        assert not counts

    def test_structural_fields_survive_seeded_fixture(self) -> None:
        payload = json.loads((FIXTURES_DIR / "redaction-seeded.json").read_text())
        out, counts = scrub_otlp_payload(payload, SALT)
        spans = out["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert [s["spanId"] for s in spans] == ["d000000000000001", "d000000000000002"]
        assert spans[0]["startTimeUnixNano"] == "1768471400000000000"
        assert counts["EMAIL"] >= 2  # name, prompt, status message
        assert counts["PRIVATE_KEY"] == 1
        rendered = json.dumps(out)
        for leaked in ("alice@example.com", "AKIAIOSFODNN7EXAMPLE", "4111 1111"):
            assert leaked not in rendered

    def test_artifact_matches_span_scrub(self) -> None:
        """Both representations of the same value carry identical
        placeholders — the cross-representation coherence the spec demands."""
        from app.importers import otlp

        payload = json.loads((FIXTURES_DIR / "redaction-seeded.json").read_text())
        artifact, _ = scrub_otlp_payload(payload, OFFLINE_SALT)
        result = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT)

        artifact_spans = artifact["resourceSpans"][0]["scopeSpans"][0]["spans"]
        artifact_prompt = next(
            a["value"]["stringValue"]
            for a in artifact_spans[0]["attributes"]
            if a["key"] == "gen_ai.prompt"
        )
        normalized = result.traces[0].spans
        by_source = {s.source_span_id: s for s in normalized}
        assert by_source["d000000000000001"].attributes["gen_ai.prompt"] == artifact_prompt
        assert by_source["d000000000000001"].name == artifact_spans[0]["name"]
        assert (
            by_source["d000000000000001"].status_message == artifact_spans[0]["status"]["message"]
        )

    def test_raw_fields_preserved_on_normalized_spans(self) -> None:
        from app.importers import otlp

        payload = json.loads((FIXTURES_DIR / "redaction-seeded.json").read_text())
        result = otlp.import_payload(payload, redaction_salt=OFFLINE_SALT)
        span = result.traces[0].spans[0]
        assert "alice@example.com" in span.raw_attributes["gen_ai.prompt"]
        assert "alice@example.com" not in span.attributes["gen_ai.prompt"]
        assert span.raw_status_message == "auth failed for alice@example.com"
