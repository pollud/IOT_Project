"""Data models and dataclasses representing domain events and commands across the IoT system."""

from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class BadgePositionEvent:
    """Event payload for badge location coordinates within a room."""
    badge_id: str
    x: float
    y: float

@dataclass
class BadgeSafetyEvent:
    """Event payload for badge safety monitoring (e.g. fall detection)."""
    badge_id: str
    fall_detected: bool

@dataclass
class EnvironmentEvent:
    """Event payload for room environmental sensors (temperature and humidity)."""
    temperature: float
    humidity: float

@dataclass
class BatteryEvent:
    """Event payload for device battery level reporting."""
    badge_id: str
    battery_level: float

@dataclass
class PropEvent:
    """Event payload for game prop interactions."""
    prop_id: str
    interaction_type: str
    value: str

@dataclass
class RoomCommand:
    """Command payload sent to control room state or actuators."""
    command: str
    target: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None

@dataclass
class AlertEvent:
    """System safety or monitoring alert event."""
    alert_type: str
    message: str
    source: str

@dataclass
class GameStatus:
    """Status payload representing the progress of a game session."""
    status: str
    time_elapsed: int

@dataclass
class HeartbeatEvent:
    """Heartbeat status event emitted by connected services and devices."""
    device_id: str
    status: str

@dataclass
class SessionEndedEvent:
    """Event emitted upon game room session completion."""
    room_id: str
    duration: int
    success: bool

@dataclass
class ConfigUpdateEvent:
    """Event emitted when a room strategy configuration is updated."""
    room_id: str
    version: str

