# MQTT Topics

This document maps all system MQTT topics to their respective data structures defined in `shared/models.py`.

## Mapping

| Topic String | Python Dataclass (`shared/models.py`) | Publisher | Subscriber | Description |
|---|---|---|---|---|
| `catalog/{room}/config-update` | `ConfigUpdateEvent` | Catalog | Room Control | Pushed when a room's strategy changes |
| `room/{room}/environment` | `EnvironmentEvent` | Room Connector | Safety Monitor, TimeSeriesDB, ThingSpeak | Periodic temp/humidity |
| `room/{room}/heartbeat` | `HeartbeatEvent` | Room Connector | TimeSeriesDB | Service alive |
| `command/room/{room}` | `RoomCommand` | Room Control | Room Connector | Unlock door, trigger actuator |
| `command/emergency` | `RoomCommand` | Safety Monitor | Room Connector | Global emergency override |
| `game/{room}/badge/{id}/position` | `BadgePositionEvent` | Badge | TimeSeriesDB | Player movement |
| `game/{room}/badge/{id}/battery` | `BatteryEvent` | Badge | TimeSeriesDB | Badge battery |
| `game/{room}/badge/{id}/safety` | `BadgeSafetyEvent` | Badge | Safety Monitor, TimeSeriesDB | Fall detection |
| `game/{room}/badge/{id}/heartbeat` | `HeartbeatEvent` | Badge | TimeSeriesDB | Badge alive |
| `game/{room}/prop/{id}/interaction` | `PropEvent` | Prop | Room Control, TimeSeriesDB | RFID/button interaction |
| `game/{room}/prop/{id}/heartbeat` | `HeartbeatEvent` | Prop | TimeSeriesDB | Prop alive (health) |
| `system/alerts` | `AlertEvent` | Safety Monitor | Telegram Bot, TimeSeriesDB | Safety / system alerts |
| `session/{room}/ended` | `SessionEndedEvent` | Room Control | Analytics | Trigger session analytics |
| `analytics/{room}/status` | `GameStatus` | Analytics | ThingSpeak, TimeSeriesDB | Post-session analytics results |
| `game/{room}/status` | `GameStatus` | Room Control | Telegram Bot | Live game state updates |
