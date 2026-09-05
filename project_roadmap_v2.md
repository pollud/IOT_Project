# Implemented roadmap

The roadmap is complete for the two-room deliverable.

- [x] object-oriented shared contracts and canonical topics
- [x] RFC 8428 JSON SenML telemetry
- [x] Dockerized Mosquitto and one folder/image per microservice type
- [x] Catalog GET/POST/PUT/DELETE, correlations and self-registration
- [x] separate Environment and Room Actuator Device Connectors
- [x] badge position, battery, heartbeat and fall data
- [x] prop RFID/button/capacitive/rotary interaction and health data
- [x] independent safety alert and emergency-unlock path
- [x] versioned, timed, recoverable Room Control FSM for two concurrent rooms
- [x] TimeSeries-owned SQLite with REST query/pagination/retention
- [x] REST-only historical Analytics with heatmaps and solve-time metrics
- [x] robust live Web Dashboard replacing Node-RED, Telegram and ThingSpeak
- [x] unit, static, frontend-build and observable end-to-end verification

Optional production extensions, outside the academic demo contract: broker TLS
and credentials, reverse-proxy login, real BME680/UWB drivers and orchestration
templates for dynamically deploying additional room containers.

