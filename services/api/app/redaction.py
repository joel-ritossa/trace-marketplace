"""Credential + PII scrubbing for trace ingestion (7_redaction.md).

Pure and deterministic: the same (value, salt) always produces the same
placeholder, so re-ingest is byte-identical and the same value reads
coherently across an upload without being linkable across uploads.

Detection tunables (entropy limits, patterns, validators) are deliberately
code, not env vars: an env-tunable ruleset would break determinism and make
REDACTION_VERSION meaningless. Bump the version on any change here.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import ipaddress
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import phonenumbers
from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class

# 1.1.0: keyword/entropy detection recurses into string values that parse as
# JSON, so key context inside stringified message blobs fires.
REDACTION_VERSION = "1.1.0"

# Fixed salt for offline paths (analysis CLI on fixtures, unit/golden tests)
# where no upload row exists. Placeholders from it are stable across runs.
OFFLINE_SALT = "offline-fixture-salt"

# --- detect-secrets credential pass -----------------------------------------

# JWTs: the plugin matches partial tokens (header.payload. without signature);
# our full-token pattern below replaces cleanly. Public IPs: ours covers v6
# and uses ipaddress validation.
_EXCLUDED_PLUGINS = {"JSON Web Token", "Public IP (ipv4)"}

_SECRET_TYPE_TO_KIND = {
    "Secret Keyword": "SECRET",
    "Base64 High Entropy String": "SECRET",
    "Hex High Entropy String": "SECRET",
    "Private Key": "PRIVATE_KEY",
}
_DEFAULT_KIND = "API_KEY"  # named provider detectors (AWS, GitHub, Stripe, …)

_PLUGINS = [
    cls()
    for secret_type, cls in sorted(get_mapping_from_secret_type_to_class().items())
    if secret_type not in _EXCLUDED_PLUGINS
]

# Agent traces are dense with high-entropy non-secrets. Skip detections that
# are id-shaped: pure hex at span-id/trace-id/sha256 lengths, or UUIDs.
# 40-hex stays flagged (legacy GitHub token shape).
_HEX_ID_LENGTHS = {16, 32, 64}
_HEX_RE = re.compile(r"[0-9a-fA-F]+\Z")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)


def _id_like(value: str) -> bool:
    if _HEX_RE.match(value) and len(value) in _HEX_ID_LENGTHS:
        return True
    return _UUID_RE.match(value) is not None


# --- pattern recognizers (credentials our way + PII) -------------------------


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _valid_card(candidate: str) -> bool:
    digits = re.sub(r"[ -]", "", candidate)
    if not 13 <= len(digits) <= 19:
        return False
    # Unseparated 13/19-digit runs are unix-millis/unix-nanos timestamp
    # shapes, everywhere in traces; a real card in those lengths is rare.
    if candidate == digits and len(digits) in (13, 19):
        return False
    return _luhn(digits)


def _valid_ssn(candidate: str) -> bool:
    area, group, serial = candidate.split("-")
    if area in ("000", "666") or area.startswith("9"):
        return False
    return group != "00" and serial != "0000"


def _valid_global_ip(candidate: str) -> bool:
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    # Loopback/private/link-local saturate traces (localhost URLs, pod IPs)
    # and identify nobody; only globally routable addresses are masked.
    return addr.is_global


@dataclass(frozen=True)
class Recognizer:
    kind: str
    pattern: re.Pattern[str]
    validator: Callable[[str], bool] | None = None

    def find(self, text: str) -> list[str]:
        return [
            m.group(0)
            for m in self.pattern.finditer(text)
            if self.validator is None or self.validator(m.group(0))
        ]


_RECOGNIZERS = [
    # Whole private-key blocks: the detect-secrets plugin only flags the
    # BEGIN line, which would leave the key body behind.
    Recognizer(
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    Recognizer(
        "JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"),
    ),
    Recognizer(
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    Recognizer(
        "CREDIT_CARD",
        re.compile(r"\b\d(?:[ -]?\d){12,18}\b"),
        _valid_card,
    ),
    Recognizer(
        "SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        _valid_ssn,
    ),
    Recognizer(
        "IP",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b"),
        _valid_global_ip,
    ),
]

# US default region so common national formats ("(212) 867-5309") validate;
# international (+xx) numbers match regardless of region.
_PHONE_REGION = "US"


def _find_phones(text: str) -> list[str]:
    if not any(ch.isdigit() for ch in text):
        return []
    return [m.raw_string for m in phonenumbers.PhoneNumberMatcher(text, _PHONE_REGION)]


# --- scrubbing ----------------------------------------------------------------


def _placeholder(kind: str, value: str, salt: str) -> str:
    digest = hmac.new(salt.encode(), value.encode(), hashlib.sha256).hexdigest()[:8]
    return f"<{kind}_{digest}>"


def _detect_secrets(text: str, key: str | None, detections: dict[str, str]) -> None:
    """detect-secrets pass for one string value, merged into `detections`.

    Two line shapes per value: the synthetic quoted `"key": "value"` form
    (keyword/entropy plugins keying off the attribute name) and the raw text
    itself (keyword patterns inline in prose, e.g. `api_key: "…"` inside a
    message — the synthetic form JSON-escapes the inner quotes those need).
    """
    synthetic = f'"{key}": {json.dumps(text)}' if key else json.dumps(text)
    for line in (synthetic, text):
        for plugin in _PLUGINS:
            for secret in plugin.analyze_line(filename="value", line=line):
                value = secret.secret_value
                if not value or _id_like(value):
                    continue
                detections.setdefault(value, _SECRET_TYPE_TO_KIND.get(secret.type, _DEFAULT_KIND))


# Stringified-JSON recursion depth: message blobs nest tool results which
# nest more JSON; beyond a few levels it's adversarial, not organic.
_JSON_RECURSE_DEPTH = 4


def _detect_in_json_blob(
    text: str, key: str | None, detections: dict[str, str], depth: int
) -> None:
    """Recurse key-context detection into string values that parse as JSON.

    Stringified blobs (`gen_ai.input.messages` etc.) hide key context like
    `"api_key": "…"` behind escaping the synthetic-line plugins can't see
    through. Detection runs per string leaf with its real key; replacement
    still happens on the original outer string, so formatting is preserved
    and nothing is re-serialized.
    """
    stripped = text.lstrip()
    if depth <= 0 or not stripped or stripped[0] not in "{[":
        return
    try:
        parsed = json.loads(text)
    except ValueError:
        return
    _walk_json_leaves(parsed, key, detections, depth)


def _walk_json_leaves(node: Any, key: str | None, detections: dict[str, str], depth: int) -> None:
    if isinstance(node, str):
        _detect_secrets(node, key, detections)
        _detect_in_json_blob(node, key, detections, depth - 1)
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk_json_leaves(v, k, detections, depth)
    elif isinstance(node, list):
        for item in node:
            _walk_json_leaves(item, key, detections, depth)


def scrub_text(text: str, salt: str, key: str | None = None) -> tuple[str, Counter[str]]:
    """Replace detected secrets/PII in one string value with placeholders.

    `key` is the attribute key the value sits under (see _detect_secrets).
    """
    counts: Counter[str] = Counter()
    if not text:
        return text, counts

    detections: dict[str, str] = {}  # value -> kind; first detector wins

    _detect_secrets(text, key, detections)
    _detect_in_json_blob(text, key, detections, _JSON_RECURSE_DEPTH)

    for recognizer in _RECOGNIZERS:
        for value in recognizer.find(text):
            detections.setdefault(value, recognizer.kind)
    for value in _find_phones(text):
        detections.setdefault(value, "PHONE")

    # Detected values must appear verbatim in the original text (a JSON-blob
    # leaf containing escapes won't; it gets skipped, never corrupted).
    detections = {v: k for v, k in detections.items() if v in text}

    # Longest first: containing matches (private-key blocks, full JWTs)
    # replace before contained ones, which then no-op.
    for value in sorted(detections, key=len, reverse=True):
        occurrences = text.count(value)
        if not occurrences:
            continue
        text = text.replace(value, _placeholder(detections[value], value, salt))
        counts[detections[value]] += occurrences
    return text, counts


def scrub_tree(value: Any, salt: str, key: str | None = None) -> tuple[Any, Counter[str]]:
    """Scrub every string value in a decoded attributes/events tree.

    Keys are never rewritten. Non-string scalars pass through untouched.
    """
    counts: Counter[str] = Counter()
    if isinstance(value, str):
        return scrub_text(value, salt, key)
    if isinstance(value, dict):
        out_dict: dict[str, Any] = {}
        for k, v in value.items():
            out_dict[k], child = scrub_tree(v, salt, k)
            counts.update(child)
        return out_dict, counts
    if isinstance(value, list):
        out_list = []
        for item in value:
            scrubbed, child = scrub_tree(item, salt, key)
            out_list.append(scrubbed)
            counts.update(child)
        return out_list, counts
    return value, counts


# --- scrubbed payload artifact (raw OTLP JSON shape) --------------------------
#
# Walks the same regions the importer stores — span name/status/attributes/
# events plus resource/scope/link attributes — and leaves structural fields
# (ids, timestamps) untouched. Key-context conventions mirror scrub_tree so
# both representations yield identical placeholders.


def _scrub_any_value(av: Any, salt: str, key: str | None, counts: Counter[str]) -> None:
    if not isinstance(av, dict):
        return
    if isinstance(av.get("stringValue"), str):
        av["stringValue"], child = scrub_text(av["stringValue"], salt, key)
        counts.update(child)
    elif isinstance(av.get("bytesValue"), str):
        av["bytesValue"], child = scrub_text(av["bytesValue"], salt, key)
        counts.update(child)
    elif isinstance(av.get("arrayValue"), dict):
        values = av["arrayValue"].get("values")
        if isinstance(values, list):
            for item in values:
                _scrub_any_value(item, salt, key, counts)
    elif isinstance(av.get("kvlistValue"), dict):
        _scrub_attribute_list(av["kvlistValue"].get("values"), salt, counts)


def _scrub_attribute_list(attributes: Any, salt: str, counts: Counter[str]) -> None:
    if not isinstance(attributes, list):
        return
    for entry in attributes:
        if isinstance(entry, dict) and isinstance(entry.get("key"), str):
            _scrub_any_value(entry.get("value"), salt, entry["key"], counts)


def _scrub_str_field(obj: dict[str, Any], field: str, salt: str, counts: Counter[str]) -> None:
    if isinstance(obj.get(field), str):
        obj[field], child = scrub_text(obj[field], salt, key=field)
        counts.update(child)


def scrub_otlp_payload(payload: dict[str, Any], salt: str) -> tuple[dict[str, Any], Counter[str]]:
    """Scrubbed copy of a raw OTLP JSON payload, plus per-kind counts.

    These counts are the stored `uploads.redaction_counts`: they cover
    resource/scope attributes, which the per-span scrub never sees.
    """
    out = copy.deepcopy(payload)
    counts: Counter[str] = Counter()
    resource_spans = out.get("resourceSpans")
    if not isinstance(resource_spans, list):
        return out, counts
    for resource_group in resource_spans:
        if not isinstance(resource_group, dict):
            continue
        resource = resource_group.get("resource")
        if isinstance(resource, dict):
            _scrub_attribute_list(resource.get("attributes"), salt, counts)
        scope_spans = resource_group.get("scopeSpans")
        if not isinstance(scope_spans, list):
            continue
        for scope_group in scope_spans:
            if not isinstance(scope_group, dict):
                continue
            scope = scope_group.get("scope")
            if isinstance(scope, dict):
                _scrub_attribute_list(scope.get("attributes"), salt, counts)
            spans = scope_group.get("spans")
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                _scrub_str_field(span, "name", salt, counts)
                if isinstance(span.get("status"), dict):
                    _scrub_str_field(span["status"], "message", salt, counts)
                _scrub_attribute_list(span.get("attributes"), salt, counts)
                for collection, fields in (("events", ("name",)), ("links", ())):
                    items = span.get(collection)
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        for f in fields:
                            _scrub_str_field(item, f, salt, counts)
                        _scrub_attribute_list(item.get("attributes"), salt, counts)
    return out, counts
