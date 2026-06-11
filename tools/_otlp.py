"""Shared OTLP JSON builders for the devdata converters
(exgentic_to_otlp.py, agent_sessions_to_otlp.py)."""

from datetime import UTC, datetime


def to_nanos(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000_000)


def any_value(value) -> dict:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [any_value(v) for v in value]}}
    if isinstance(value, str):
        try:
            return {"intValue": str(int(value))} if value.lstrip("-").isdigit() else {"stringValue": value}
        except ValueError:
            return {"stringValue": value}
    return {"stringValue": str(value)}


def attr_list(attributes: dict) -> list[dict]:
    return [{"key": k, "value": any_value(v)} for k, v in attributes.items() if v is not None]
