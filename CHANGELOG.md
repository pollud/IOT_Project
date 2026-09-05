# Changelog

## Corrected two-room release

- unified every producer/subscriber on one canonical MQTT namespace;
- replaced the ten incomplete room aliases with two complete, independently
  executable rooms and exact device/strategy correlations;
- split Environment Connector and Room Actuator Connector as required by the
  proposal;
- implemented SenML telemetry, unique MQTT identities and actor self-registration;
- added complete Catalog CRUD and REST-only strategy discovery/hot reload;
- completed badge and prop telemetry/health functionality;
- fixed FSM duration, terminal detection, timed transitions and retained recovery;
- made TimeSeries the sole SQLite owner and added its REST event API;
- replaced placeholder Analytics formulas with historical calculations;
- made the browser consume SSE and added controls, alerts, presence, charts and
  heatmaps needed to replace Node-RED, Telegram and ThingSpeak;
- hardened Compose startup, health checks, local port binding, named persistence
  and non-root service images;
- removed the stale pre-populated database from the deliverable;
- replaced permissive phase scripts with deterministic unit and black-box tests.

