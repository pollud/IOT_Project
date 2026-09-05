"""Typed semantic payloads exchanged outside SenML sensor telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PropEvent:
    room_id: str
    prop_id: str
    interaction_type: str
    value: str
    timestamp: float


@dataclass(frozen=True)
class RoomCommand:
    room_id: str
    command: str
    target: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    issued_by: str = "system"


@dataclass(frozen=True)
class AlertEvent:
    room_id: str
    alert_type: str
    severity: str
    message: str
    source: str
    timestamp: float


@dataclass(frozen=True)
class SessionEvent:
    room_id: str
    session_id: str
    timestamp: float
    duration_seconds: float | None = None
    success: bool | None = None


@dataclass(frozen=True)
class GameStatus:
    room_id: str
    session_id: str
    current_state: str
    strategy_version: str
    started_at: float
    state_entered_at: float
    updated_at: float
    completed: bool = False


@dataclass(frozen=True)
class TransitionEvent:
    room_id: str
    session_id: str
    from_state: str
    to_state: str
    trigger: str
    trigger_id: str | None
    elapsed_seconds: float
    timestamp: float


@dataclass(frozen=True)
class ConfigUpdateEvent:
    room_id: str
    version: str
    timestamp: float
