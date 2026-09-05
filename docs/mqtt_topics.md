# Canonical MQTT contract

All services import `shared/topics.py`; ad-hoc topic construction is forbidden.
Telemetry and device health payloads are RFC 8428 JSON SenML arrays. Commands,
alerts, FSM status, transitions and session events are JSON objects.

| Topic | QoS | Publisher | Subscribers | Payload |
| --- | ---: | --- | --- | --- |
| `room/<room>/environment/<sensor>/telemetry` | 0 | Environment Connector | Safety, TimeSeries, Dashboard | SenML temperature, humidity, CO2, VOC |
| `game/<room>/badge/<badge>/position` | 0 | Badge Connector | TimeSeries, Dashboard | SenML x/y metres |
| `game/<room>/badge/<badge>/battery` | 0 | Badge Connector | TimeSeries, Dashboard | SenML battery percent |
| `game/<room>/badge/<badge>/heartbeat` | 0 | Badge Connector | TimeSeries, Dashboard | SenML online flag |
| `game/<room>/badge/<badge>/safety` | 1 | Badge Connector | Safety, TimeSeries, Dashboard | SenML fall flag/acceleration |
| `game/<room>/prop/<prop>/interaction` | 1 | Prop Connector or Dashboard | Room Control, TimeSeries, Dashboard | SenML interaction type/value |
| `game/<room>/prop/<prop>/health` | 0 | Prop Connector | TimeSeries, Dashboard | SenML online/RSSI |
| `game/<room>/prop/<prop>/heartbeat` | 0 | Prop Connector | TimeSeries, Dashboard | SenML online flag |
| `command/room/<room>` | 1 | Room Control or Dashboard | Room Actuator, Room Control | `RoomCommand` JSON |
| `command/emergency/<room>` | 1 | Safety Monitor | Room Actuator, TimeSeries | emergency `RoomCommand` |
| `game/<room>/status` | 1 retained | Room Control | Dashboard, TimeSeries, recovering Room Control | `GameStatus` |
| `game/<room>/transition` | 1 | Room Control | TimeSeries, Dashboard | solve-time `TransitionEvent` |
| `session/<room>/started` | 1 | Room Control | TimeSeries, Dashboard | `SessionEvent` |
| `session/<room>/ended` | 1 | Room Control | TimeSeries, Analytics, Dashboard | `SessionEvent` with real duration/success |
| `system/alerts` | 1 | Safety Monitor | TimeSeries, Dashboard | critical `AlertEvent` |
| `catalog/<room>/config-update` | 1 retained | Catalog | Room Control | versioned `ConfigUpdateEvent` |
| `analytics/<room>/summary` | 1 | Analytics | Dashboard | post-session room statistics |
| `status/<unique_client_id>` | 1 retained | every actor | Catalog, TimeSeries, Dashboard | heartbeat/LWT presence JSON |

## SenML example

```json
[
  {
    "bn": "urn:escape-room:room1:environment:env1:",
    "bt": 1760000000.0,
    "n": "temperature",
    "v": 22.4,
    "u": "Cel"
  },
  {"n": "humidity", "v": 47.2, "u": "%RH"},
  {"n": "co2", "v": 680.0, "u": "ppm"},
  {"n": "voc", "v": 0.34, "u": "mg/m3"}
]
```

## Room command example

```json
{
  "room_id": "room1",
  "command": "set_lights",
  "target": null,
  "parameters": {"color": "warning_amber"},
  "issued_by": "room_control_room1"
}
```

