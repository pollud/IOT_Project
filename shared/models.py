from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class BadgePositionEvent:
    badge_id: str
    x: float
    y: float

@dataclass
class BadgeSafetyEvent:
    badge_id: str
    fall_detected: bool

@dataclass
class EnvironmentEvent:
    temperature: float
    humidity: float

@dataclass
class BatteryEvent:
    badge_id: str
    battery_level: float

@dataclass
class PropEvent:
    prop_id: str
    interaction_type: str
    value: str

@dataclass
class RoomCommand:
    command: str
    target: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None

@dataclass
class AlertEvent:
    alert_type: str
    message: str
    source: str

@dataclass
class GameStatus:
    status: str
    time_elapsed: int

@dataclass
class HeartbeatEvent:
    device_id: str
    status: str

@dataclass
class SessionEndedEvent:
    room_id: str
    duration: int
    success: bool

@dataclass
class ConfigUpdateEvent:
    room_id: str
    version: str
