# MQTT API

The authoritative topic table is [mqtt_topics.md](mqtt_topics.md). This document
defines behavioral guarantees.

## Guarantees

- MQTT client IDs are validated and unique per service/room instance.
- QoS 0 is used for replaceable high-frequency telemetry.
- QoS 1 is used for commands, safety, transitions and session lifecycle events.
- Current FSM state, Catalog configuration updates and service presence are
  retained.
- Every Last Will publishes `status=offline` on `status/<client_id>`.
- Every room-scoped topic carries the room ID in a fixed segment, allowing
  storage and analytics correlation without inspecting arbitrary text.

## Prop interaction

Topic: `game/room1/prop/pipboy/interaction`

```json
[
  {
    "bn": "urn:escape-room:room1:prop:pipboy:",
    "bt": 1760000000.0,
    "n": "interaction_type",
    "vs": "rfid"
  },
  {"n": "value", "vs": "scanned"}
]
```

Room Control checks all of `prop_id`, `interaction_type` and `value` against the
current FSM state. A non-matching but valid event is logged and ignored.

## Safety path

A `fall_detected=true` SenML record produces two QoS 1 messages:

1. `system/alerts` for live GUI awareness and historical persistence;
2. `command/emergency/<room>` for an independent actuator unlock.

The emergency path does not depend on Room Control.

