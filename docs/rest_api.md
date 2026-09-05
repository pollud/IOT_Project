# REST API

All responses are JSON except the Dashboard HTML/assets and SSE stream.

## Game Catalog - port 8080

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | registry and MQTT health |
| GET/POST/PUT/DELETE | `/services?name=<id>` | complete service CRUD |
| GET/POST/PUT/DELETE | `/devices?device_id=<id>` | complete device CRUD |
| GET/POST/PUT/DELETE | `/rooms?room_id=<id>` | complete room CRUD with correlation guard |
| POST | `/register` | idempotent actor self-registration |
| GET | `/config/<room_id>` | validated room strategy retrieval |
| PUT | `/config/<room_id>` | atomic strategy update and MQTT hot-reload notification |

POST rejects duplicates with 409; PUT replaces an identified entity. A room
cannot be deleted while registered devices still reference it.

## Device Connectors

| Port | Method/path | Purpose |
| ---: | --- | --- |
| 8101 / 8201 | `GET /health` | latest environment reading and connector state |
| 8101 / 8201 | `GET /calibration` | BME680 calibration metadata |
| 8102 / 8202 | `GET /health` | actuator state and bounded command history |
| 8103 / 8203 | `GET /battery[?badge_id=...]` | badge battery status required by proposal |
| 8103 / 8203 | `POST /force_fall?badge_id=...` | deterministic safety demonstration |
| 8104 / 8204 | `GET /health` | configured prop health and last interactions |
| 8104 / 8204 | `POST /trigger` | validated physical-prop simulator input |

## TimeSeries Adapter - port 8085

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | queue/write counters and stored event count |
| GET | `/events` | historical event query |
| POST | `/reset?confirm=true` | explicit demo-data purge |

`/events` accepts `room_id`, `event_type`, `from_ts`, `to_ts`, `limit` (max
5000), `offset` and `order=asc|desc`. Results are ordered by timestamp and ID.

## Analytics - port 8086

All endpoints accept a period in `1h`, `24h`, `7d`, `30d`, `all` where relevant.

| Method | Path |
| --- | --- |
| GET | `/health` |
| GET | `/stats/room?room_id=<id>&period=<period>` |
| GET | `/stats/prop?prop_id=<id>&room_id=<id>&period=<period>` |
| GET | `/stats/environment?room_id=<id>&period=<period>` |
| GET | `/stats/history?room_id=<id>&period=<period>&limit=<n>` |
| GET | `/stats/heatmap?room_id=<id>&period=<period>` |
| GET | `/stats/bottlenecks[?room_id=<id>]&period=<period>` |
| GET | `/stats/safety[?room_id=<id>]&period=<period>` |
| GET | `/stats/maintenance[?room_id=<id>]&period=<period>` |
| GET | `/stats/game_center?period=<period>` |
| POST | `/stats/reset` |

Analytics has no SQLite mount. It obtains all events from the TimeSeries REST
API with timeouts and pagination.

## Web Dashboard - port 8087

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | backend/MQTT/SSE health |
| GET | `/api/rooms` | correlated room definitions |
| GET | `/api/status` | initial live cache snapshot |
| GET | `/api/presence` | MQTT LWT/heartbeat snapshot |
| GET | `/api/stream` | real Server-Sent Events stream |
| POST | `/api/command` | validated Game Master command gateway |
| GET | `/api/strategy/<room_id>` | Catalog proxy |
| GET/POST | `/api/stats/*` | allow-listed Analytics proxy |

Supported commands: `reset`, `start`, `unlock`, `lock`, `set_lights`,
`play_audio`, `trigger_prop`. Prop commands are checked against Catalog room
configuration before MQTT publication.

