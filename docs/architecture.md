# Architecture Overview

## Objective
Define the architecture for the IoT escape-room platform. The platform is built around an asynchronous MQTT event bus, CherryPy microservices, embedded SQLite timeseries storage, autonomous Room Control FSMs, a safety supervisor, and a unified Web Dashboard acting as the **Game Master Command Center**.

## Component Overview
- **Game Catalog (`:8080`)**: Single source of truth for rooms, devices, configurations, and dynamic discovery. Provides REST APIs and MQTT config update broadcasts.
- **Room Connector (`:8081`)**: Interfacing service handling room environment telemetry (temperature, humidity) and electronic actuator relays (mag-locks, lights, sound).
- **Badge Connector (`:8082`)**: Wearable telemetry service tracking player spatial coordinates, battery levels, and fall detection.
- **Prop Connector (`:8083`)**: Interactive puzzle prop service handling player inputs (buttons, RFID sensors, keypads).
- **Room Control FSM**: Decentralized, autonomous state machine managing game progress, puzzle progression, and time-based schedules.
- **Safety Monitor**: Independent, high-priority safety supervisor triggering emergency mag-lock overrides and alarms.
- **TimeSeriesDB Adapter**: High-throughput SQLite persistence layer with in-memory batch writing and automated telemetry retention pruning.
- **Analytics Engine (`:8084`)**: Post-game analytics engine computing solve durations, puzzle bottlenecks, safety scores, and spatial heatmaps.
- **Web Dashboard (`:8087`)**: Single unified **Game Master Command Center** providing real-time Server-Sent Events (SSE) streaming, live room matrices, actuator controls, manual puzzle triggers, alert banners, and analytics visualization.

## Directory Structure
```
project/
  docs/
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
  simulators/
  tests/
    phase_gates/
    integration/
    stress/
  docker-compose.yml
  README.md
```

## Data Storage
- TimeSeriesDB uses **SQLite** (`data/events.db`) with composite indexes on `(topic, timestamp)` and batch insert optimizations (`executemany`).
- Strategy rulesets and service registrations are persisted in `config/`.
