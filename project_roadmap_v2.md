# Project roadmap — v2

Corrected from your draft. Changes from v1:

1. **Analytics Engine and TimeSeriesDB Adapter were swapped.** Your phase breakdown had Analytics (10) before TimeSeriesDB (11), but your own summary table had them the other way round — and the table was right. Analytics can't query history that doesn't exist yet. Fixed: TimeSeriesDB is now phase 10, Analytics is phase 11.
2. **Room Connector didn't subscribe to the emergency-override topic.** Safety Monitor (phase 8) publishes `command/emergency`, but Room Connector (phase 5) only subscribed to `command/room` — it would need reopening once phase 8 landed. Fixed: both subscriptions are in phase 5 from the start.
3. **Game Catalog didn't publish config updates.** The whole point of that mechanism was to stop Room Control Logic's cached ruleset going stale — but phase 3 never lists publishing it, and phase 9 never lists subscribing to it. Fixed: both sides are explicit now.
4. **Testing was 100% deferred to phase 16.** Added a concrete, scriptable **Verify** step to every phase — not "it works," but the actual command/assertion that proves it.
5. **The FSM had no time-based transitions**, despite your own spec saying Room Control Logic manages puzzles "depending on player actions *and* game time." Added `scheduler.py`, plus a task to actually author one demo `room_strategy.json` — an engine with no content isn't a demo.
6. **SQLite vs. InfluxDB was left open with no owner for the decision.** Defaulted to SQLite for zero extra moving parts; swap to InfluxDB later if you want it.
7. **Phase 15's flow diagram was a strict pipeline**, but the real system is parallel and dual-triggered. Rewritten as a scenario checklist, run across 2+ concurrent rooms.

Everything else — the milestone philosophy, shared library first, heartbeat + LWT, `last_seen` tracking — was already right and is unchanged.

---

## Phase 0 — Project design

Goal: define the entire architecture before writing code.

Deliverables:
```
docs/
  architecture.md
  mqtt_topics.md      # full topic strings, room + device parameterized —
                       # reuse game/<room>/badge/<id>/position, etc.
  rest_api.md
  fsm.md               # state/transition/action schema AND the time-trigger model
  sequence_diagrams.md
  phase_gates.md       # NEW — the Verify command for every phase, written once
                         # here so later phases just execute it
```

Tasks:
- define every MQTT topic (full strings, room + device parameterized)
- define every REST endpoint
- define JSON payloads
- define directory structure
- define FSM configuration format, including how time-based transitions are expressed
- define configuration files
- **decide SQLite vs. InfluxDB now** (default: SQLite) so phase 2 isn't guessing
- write the Verify command for every subsequent phase into `phase_gates.md`

Verify: every topic in `mqtt_topics.md` maps to a dataclass name in the (not-yet-written) `shared/models.py` list below, and phases 1–16 each have an entry in `phase_gates.md`.

---

## Phase 1 — Shared Python library

Repository: `shared/`
Goal: everything imports from here; no duplicated payload definitions anywhere.

Create:
```
shared/
  events.py
  topics.py
  config.py
  constants.py
  models.py
  fsm_schema.py   # NEW — room_strategy.json's schema lives here, not just inside
                    # room_control's loader, so phase 9 validates against a shared contract
  utils.py
```

Implement:
- dataclasses: `BadgePositionEvent`, `BadgeSafetyEvent`, `EnvironmentEvent`, `BatteryEvent`, `PropEvent`, `RoomCommand`, `AlertEvent`, `GameStatus`, `HeartbeatEvent`, `SessionEndedEvent`, `ConfigUpdateEvent`
- MQTT topic builder: `build_topic(room, device, event)`
- configuration loader
- JSON serializer
- `RoomStrategySchema` (pydantic or jsonschema) validating `room_strategy.json` at load time

Verify: a unit test round-trips every dataclass through serialize → deserialize and asserts equality; `python -c "import shared"` succeeds with no service code written yet.

---

## Phase 2 — Infrastructure

Goal: system boots with one command — the skeleton only, no service logic yet.

Tasks:
- Mosquitto container (the actual "deploy" here — CherryPy isn't something you deploy, it's the library each service uses internally; SQLite is an embedded file, not a container)
- `docker-compose.yml` with just the broker for now — each later phase adds its own service entry when that service is actually built, not all ten upfront
- `config/broker.json`, `config/catalog.json`, `config/rooms.json`

Verify: `docker-compose up` starts the broker cleanly; `mosquitto_pub` / `mosquitto_sub` round-trip a message on a scratch topic.

---

## Phase 3 — Game Catalog

Repository: `services/catalog`
Goal: single source of truth.

Tasks:
- CherryPy server, REST: `GET /services`, `GET /devices`, `GET /rooms`, `GET /config/<room>`, `POST /register`
- store: devices, rooms, strategies, versions, `last_seen`
- maintain API keys, registered services
- **publish `catalog/<room>/config-update` (MQTT, retained) whenever a room's config changes** — phase 9's FSM subscribes to this, so it must exist now
- Catalog is a REST provider *and* a light MQTT publisher — run the MQTT client loop in a background thread inside the same CherryPy process

Verify: script registers a fake device via `POST /register`, confirms it via `GET /devices`; a manual config edit is followed by a message on `catalog/<room>/config-update` within 1s.

---

## Phase 4 — MQTT framework

Goal: common MQTT abstraction.

Tasks:
- `shared/mqtt.py`: publisher, subscriber, reconnect, heartbeat, last will, QoS, logging

Verify: kill the broker mid-session, confirm `MQTTClient` reconnects and resumes without crashing the calling service; kill a client ungracefully, confirm its last-will message actually arrives.

---

## Phase 5 — Room connector

Goal: single Raspberry Pi service (or simulator) per room.

Internal modules: `EnvironmentSensor`, `ActuatorControl`

CherryPy REST: `GET calibration`, `GET actuator health`

MQTT:
- publish: `environment`, `heartbeat`
- **subscribe: `command/room` (from Room Control) *and* `command/emergency` (from Safety Monitor) — both from day one**, since phase 8 needs the second one already working

Verify: publish a `command/room` unlock and a `command/emergency` override separately, confirm the simulated relay logs both and distinguishes them; confirm `environment` keeps publishing on schedule throughout.

---

## Phase 6 — Badge connector

Tasks: simulate movement, battery, fall detection.
Publish: `position`, `battery`, `heartbeat`, `safety`

Verify: subscribe to all four topics for 60s, assert every one fires at least once, including a forced fall event.

---

## Phase 7 — Prop connector

Tasks: simulate button, RFID, capacitive sensor.
Publish: `interaction`, `health`, `heartbeat`

Verify: trigger each simulated interaction type once, assert exactly one `interaction` message per trigger, correctly tagged with the right prop id.

---

## Phase 8 — Safety Monitor

Subscribe: `badge`, `environment`
Logic: fall → unlock room → alert
Publish: `system/alerts`, `command/emergency`

Verify: publish a synthetic fall event, assert both `command/emergency` and `system/alerts` fire within ~2s, and (from phase 5) the room connector actually logs the unlock.

---

## Phase 9 — Room Control FSM

The most important phase.

Repository: `services/room_control`

Modules:
```
fsm.py
loader.py        # validates against shared.fsm_schema.RoomStrategySchema
actions.py
controller.py
scheduler.py      # NEW — timer-based transitions: elapsed game time, countdowns,
                    # idle-hint triggers. Without this the FSM only ever reacts to
                    # events and can't do anything "depending on game time"
```

Tasks:
- load `room_strategy.json`
- **author at least one complete demo `room_strategy.json`** — states, transitions, actions, at least one time-based trigger
- implement FSM: `current_state`, `transition()`, `execute_action()`
- actions: `unlockDoor`, `playAudio`, `setLights`, `publishStatus`
- subscribe `catalog/<room>/config-update` → revalidate + hot-swap the cached ruleset, no restart

Verify: drive the demo strategy through a scripted sequence of prop/timer events, assert it reaches the solved end state; push a config-update mid-run, confirm the running instance picks it up without a restart.

---

## Phase 10 — TimeSeriesDB Adapter

*(moved up — was phase 11)*

Tasks:
- subscribe: all telemetry
- store: SQLite (default)
- REST: `GET /events?room=&from=&to=&type=`

Verify: publish 100 synthetic telemetry messages across two rooms, `GET /events` for one room, assert exactly that room's messages come back, correctly time-ordered.

---

## Phase 11 — Analytics Engine

*(moved down — was phase 10; now correctly depends on phase 10 existing)*

Repository: `services/analytics`

Tasks:
- subscribe: `session/ended`
- REST: retrieve historical events from the TimeSeriesDB Adapter — the only place session data comes from
- compute: heatmap, solve times, completion time, player path
- publish: `analytics`

Verify: kill and restart Analytics Engine mid-session, then trigger `session/ended` — output should be identical, since nothing it needs lives anywhere but the TimeSeriesDB Adapter.

---

## Phase 12 — Analytics REST Engine

Repository: `services/analytics`

Tasks:
- REST API: provide `/stats/room`, `/stats/prop`, `/stats/environment`, `/stats/history`, `/stats/bottlenecks`, `/stats/safety`, `/stats/game_center`, `/stats/heatmap`
- Query SQLite `events.db` directly to aggregate solve metrics and spatial heatmaps

Verify: assert all `/stats/*` endpoints return valid data structures with accurate math.

---

## Phase 13 — Web Dashboard Command Gateway

Repository: `services/web_dashboard`

Tasks:
- REST API: `POST /api/command` dispatcher
- Publish manual actuation commands to MQTT (`unlockDoor`, `reset`, `trigger_prop`, `set_lights`, `play_audio`)
- Maintain sub-second command delivery latency

Verify: `/api/command` returns in under ~1s and the corresponding command arrives on the MQTT bus.

---

## Phase 14 — Web Dashboard Real-Time SSE Stream

Repository: `services/web_dashboard`

Tasks:
- Server-Sent Events (SSE): `GET /api/stream`
- Bridge MQTT telemetry (`room/+/environment`, `room/+/status`, `system/alerts`, `status/+`) directly to connected frontend clients
- Host responsive Web UI Single Page Application on `:8087`

Verify: browser client connects to `/api/stream` and receives live events without continuous HTTP polling.

---

## Phase 15 — End-to-end multi-room integration

Parallel multi-room integration scenario:
- Run 2+ rooms concurrently
- Badges move and props get interacted with throughout, in both rooms
- Confirm Room Control's FSM transitions correctly in each room, independently
- Confirm Safety Monitor's emergency path works without depending on Room Control
- End one session; confirm the other room is unaffected
- Confirm TimeSeriesDB has the full history, correctly separated by room
- Confirm Analytics computes correct per-room metrics
- Confirm Web Dashboard displays real-time state and controls both rooms seamlessly

Verify: automate the multi-room simulation as one script (`game_center_simulator.py` / `verify_phase_15.py`).

---

## Phase 16 — Testing & hardening

Unit: FSM, Catalog, Analytics, shared models.
Integration: MQTT, REST, startup, shutdown, recovery.
Stress: Multi-room high-frequency telemetry load testing.

---

## Development order (critical)

| Step | Deliverable | Stop condition |
|---|---|---|
| 1 | Architecture docs + phase gates | Every phase has a written Verify step |
| 2 | Shared library | All services compile against common models |
| 3 | Infrastructure | Broker + compose skeleton running |
| 4 | Game Catalog | Registration, config retrieval, config-update all work |
| 5 | MQTT framework | Reconnect, heartbeat, LWT verified |
| 6 | Room connector | Both command topics handled |
| 7 | Badge connector | All four topics verified |
| 8 | Prop connector | Interaction + health verified |
| 9 | Safety Monitor | Emergency path verified end to end |
| 10 | Room Control FSM | Demo room playable; config hot-swap verified |
| 11 | TimeSeriesDB Adapter | History queryable, room-separated |
| 12 | Analytics Engine | Survives a restart mid-session |
| 13 | Web Command Gateway | Instant `/api/command`, working manual commands |
| 14 | Web Dashboard SSE Stream | Real-time events delivered to UI |
| 15 | Multi-room integration | No cross-room leakage |
| 16 | Testing & hardening | Justified stress numbers, full suite green |

---

## Final repository structure

```
project/
  docs/
    architecture.md
    mqtt_topics.md
    rest_api.md
    fsm.md
    sequence_diagrams.md
    phase_gates.md
  shared/
  config/
  services/
    catalog/
    room_connector/
    badge_connector/
    prop_connector/
    room_control/
    safety_monitor/
    timeseries_adapter/
    analytics/
    web_dashboard/
  tests/
    phase_gates/
    integration/
    stress/
  docker-compose.yml
  README.md
```

One process note: tag a git commit at the end of every phase once its Verify step passes (`git tag phase-05-room-connector`, etc.). If phase 12 breaks something, you want a clean "last known good" to diff against instead of guessing which of the last five phases introduced the bug.
