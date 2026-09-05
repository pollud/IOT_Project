"""Canonical MQTT topic contract for the whole platform.

All producers and consumers import these helpers. No service builds an MQTT
topic with ad-hoc string concatenation.
"""

from __future__ import annotations

from shared.config import validate_identifier

SYSTEM_ALERTS = "system/alerts"
SERVICE_STATUS_WILDCARD = "status/+"


def environment(room_id: str, sensor_id: str = "env1") -> str:
    room = validate_identifier(room_id, "room_id")
    sensor = validate_identifier(sensor_id, "sensor_id")
    return f"room/{room}/environment/{sensor}/telemetry"


def environment_wildcard() -> str:
    return "room/+/environment/+/telemetry"


def badge(room_id: str, badge_id: str, event: str) -> str:
    if event not in {"position", "battery", "safety", "heartbeat"}:
        raise ValueError(f"Unsupported badge event: {event}")
    room = validate_identifier(room_id, "room_id")
    device = validate_identifier(badge_id, "badge_id")
    return f"game/{room}/badge/{device}/{event}"


def badge_wildcard(event: str = "+") -> str:
    if event != "+" and event not in {"position", "battery", "safety", "heartbeat"}:
        raise ValueError(f"Unsupported badge event: {event}")
    return f"game/+/badge/+/{event}"


def prop(room_id: str, prop_id: str, event: str) -> str:
    if event not in {"interaction", "health", "heartbeat"}:
        raise ValueError(f"Unsupported prop event: {event}")
    room = validate_identifier(room_id, "room_id")
    device = validate_identifier(prop_id, "prop_id")
    return f"game/{room}/prop/{device}/{event}"


def prop_wildcard(room_id: str = "+", event: str = "+") -> str:
    if room_id != "+":
        validate_identifier(room_id, "room_id")
    if event != "+" and event not in {"interaction", "health", "heartbeat"}:
        raise ValueError(f"Unsupported prop event: {event}")
    return f"game/{room_id}/prop/+/{event}"


def room_command(room_id: str) -> str:
    return f"command/room/{validate_identifier(room_id, 'room_id')}"


def emergency_command(room_id: str) -> str:
    return f"command/emergency/{validate_identifier(room_id, 'room_id')}"


def game_status(room_id: str) -> str:
    return f"game/{validate_identifier(room_id, 'room_id')}/status"


def game_transition(room_id: str) -> str:
    return f"game/{validate_identifier(room_id, 'room_id')}/transition"


def session(room_id: str, event: str) -> str:
    if event not in {"started", "ended"}:
        raise ValueError(f"Unsupported session event: {event}")
    return f"session/{validate_identifier(room_id, 'room_id')}/{event}"


def catalog_update(room_id: str) -> str:
    return f"catalog/{validate_identifier(room_id, 'room_id')}/config-update"


def analytics_summary(room_id: str) -> str:
    return f"analytics/{validate_identifier(room_id, 'room_id')}/summary"


def service_status(client_id: str) -> str:
    return f"status/{validate_identifier(client_id, 'client_id')}"


def room_from_topic(topic: str) -> str | None:
    """Return the correlated room ID for every room-scoped canonical topic."""
    parts = topic.split("/")
    if len(parts) >= 2 and parts[0] in {"room", "game", "session", "catalog", "analytics"}:
        return parts[1]
    if len(parts) >= 3 and parts[0] == "command" and parts[1] in {"room", "emergency"}:
        return parts[2]
    return None


def event_type_from_topic(topic: str) -> str:
    parts = topic.split("/")
    if topic == SYSTEM_ALERTS:
        return "alert"
    if parts[0] == "status":
        return "presence"
    if parts[0] == "room" and len(parts) == 5:
        return "environment"
    if parts[0] == "game" and len(parts) == 5 and parts[2] == "badge":
        return f"badge_{parts[4]}"
    if parts[0] == "game" and len(parts) == 5 and parts[2] == "prop":
        return f"prop_{parts[4]}"
    if parts[0] == "game" and len(parts) == 3:
        return f"game_{parts[2]}"
    if parts[0] == "session" and len(parts) == 3:
        return f"session_{parts[2]}"
    if parts[0] == "command":
        return "command"
    return "other"
