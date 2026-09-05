"""Small RFC 8428 JSON SenML encoder/decoder used by device connectors."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from numbers import Real
from typing import Any

VALUE_KEYS = ("v", "vs", "vb", "vd")


def _value_field(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool):
        return "vb", value
    if isinstance(value, Real):
        return "v", value
    if isinstance(value, str):
        return "vs", value
    raise TypeError(f"Unsupported SenML value type: {type(value).__name__}")


def make_pack(
    base_name: str,
    measurements: Iterable[tuple[str, Any, str | None]],
    timestamp: float | None = None,
) -> list[dict[str, Any]]:
    """Build a compact SenML pack from ``(name, value, unit)`` tuples."""
    records: list[dict[str, Any]] = []
    for index, (name, value, unit) in enumerate(measurements):
        record: dict[str, Any] = {"n": name}
        if index == 0:
            record["bn"] = base_name
            record["bt"] = float(timestamp if timestamp is not None else time.time())
        key, encoded = _value_field(value)
        record[key] = encoded
        if unit:
            record["u"] = unit
        records.append(record)
    if not records:
        raise ValueError("A SenML pack must contain at least one measurement")
    return records


def loads(payload: str | bytes | list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = json.loads(payload) if isinstance(payload, str | bytes) else payload
    if not isinstance(raw, list) or not raw:
        raise ValueError("SenML JSON payload must be a non-empty array")
    base_name = ""
    base_time = 0.0
    decoded: list[dict[str, Any]] = []
    for record in raw:
        if not isinstance(record, dict):
            raise TypeError("Every SenML record must be an object")
        base_name = str(record.get("bn", base_name))
        base_time = float(record.get("bt", base_time))
        value_keys = [key for key in VALUE_KEYS if key in record]
        if len(value_keys) != 1 or "n" not in record:
            raise ValueError("Each SenML record needs one value field and a name")
        key = value_keys[0]
        decoded.append(
            {
                "name": f"{base_name}{record['n']}",
                "short_name": str(record["n"]),
                "value": record[key],
                "unit": record.get("u"),
                "timestamp": base_time + float(record.get("t", 0.0)),
            }
        )
    return decoded


def values(payload: str | bytes | list[dict[str, Any]]) -> dict[str, Any]:
    return {record["short_name"]: record["value"] for record in loads(payload)}


def timestamp(payload: str | bytes | list[dict[str, Any]], default: float | None = None) -> float:
    decoded = loads(payload)
    return decoded[0]["timestamp"] if decoded else (default or time.time())
