# REST APIs

## Game Catalog (`services/catalog` — Port `8080`)
- `GET /services`: List registered services, their `last_seen` timestamps and online statuses.
- `GET /devices`: List registered IoT devices (sensors, props, badges).
- `GET /rooms`: List available room IDs.
- `GET /config/<room>`: Get the current `strategy_<room>.json` for a specific room.
- `GET /health`: Aggregated health check reporting total services and devices.
- `POST /register`: Dynamically register or update a service or device.

## Room Connector (`services/room_connector` — Port `8081`)
- `GET /actuator/health`: Retrieve actuator execution logs and health status.

## Badge Connector (`services/badge_connector` — Port `8082`)
- `POST /force_fall`: Trigger a simulated player fall safety event.

## Prop Connector (`services/prop_connector` — Port `8083`)
- `POST /trigger_button`: Trigger a simulated button interaction on the prop.

## Analytics Engine (`services/analytics` — Port `8084`)
- `GET /stats/room?room_id=<id>&period=<1h|24h|7d|all>`: Average solve duration and session count.
- `GET /stats/prop?prop_id=<id>`: Total usage and interaction count for a puzzle prop.
- `GET /stats/environment?room_id=<id>&period=<1h|24h|7d|all>`: Min, max, average temp and humidity.
- `GET /stats/history?room_id=<id>&period=<1h|24h|7d|all>`: Historical environmental time-series series.
- `GET /stats/bottlenecks`: Puzzle chokepoints and bottleneck severity rankings.
- `GET /stats/safety`: Room Physical Strain & Safety Comfort Index (0–100%).
- `GET /stats/maintenance`: Hardware diagnostics and battery replacement warnings.
- `GET /stats/game_center`: Facility-wide KPIs across all 10 theme rooms.
- `GET /stats/heatmap?room_id=<id>`: Spatial coordinate matrix for player positioning.
- `POST /stats/reset`: Purge database for clean test runs.

## Web Dashboard (`services/web_dashboard` — Port `8087`)
- `GET /api/stream`: **Server-Sent Events (SSE)** real-time stream of all MQTT telemetry and alerts.
- `GET /api/status`: Cached state of all monitored rooms.
- `GET /api/presence`: Active service and device presence status.
- `POST /api/command`: Game Master manual override gateway (unlock, reset, prop trigger, lighting, audio).
- `GET /api/stats/*`: Transparent proxy to Analytics service endpoints (`:8084/stats/*`).
- `GET /api/strategy/<room_id>`: Transparent proxy to Catalog service strategy endpoint (`:8080/config/<room_id>`).
