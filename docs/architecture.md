# Architecture Overview

## Objective
Define the architecture for the IoT escape-room platform. The platform is based on CherryPy + Python, MQTT, one Raspberry Pi-backed Room Connector, simulated Badge/Prop connectors, a Room Control FSM, and an analytics pipeline through a TimeSeriesDB Adapter to ThingSpeak.

## Component Overview
- **Game Catalog**: Single source of truth for rooms, devices, configurations. Provides REST APIs and MQTT config updates.
- **Room Connector**: Pi service handling environment sensors and actuators via REST and MQTT.
- **Badge Connector (Simulator)**: Simulates player positions, falls, and battery via MQTT.
- **Prop Connector (Simulator)**: Simulates prop interactions via MQTT.
- **Safety Monitor**: Evaluates environment and badge safety. Generates alerts and emergency overrides.
- **Room Control FSM**: State machine to manage game progress, execute actions, and handle time-based events.
- **TimeSeriesDB Adapter**: Persists all telemetry. **Decision**: using **SQLite** as the storage backend (no InfluxDB).
- **Analytics Engine**: Computes analytics and player paths when a session ends.
- **ThingSpeak Adapter**: Pushes filtered aggregated analytics to ThingSpeak, and serves a `/history` API for local dashboards to prevent direct ThingSpeak polling.
- **Telegram Bot**: Operator bot for manual control and status.
- **Node-RED**: Local dashboard for monitoring and manual control.

## Directory Structure
```
project/
  docs/
  shared/
  config/
  docker/
  services/
    catalog/
    room_connector/
    badge_connector/
    prop_connector/
    room_control/
    safety_monitor/
    timeseries_adapter/
    analytics/
    thingspeak_adapter/
    telegram_bot/
  simulators/
  tests/
    phase_gates/
    integration/
    stress/
  docker-compose.yml
  README.md
```

## Data Storage
- TimeSeriesDB will use **SQLite** as the default backend. No external databases are required.
- Configuration is loaded from `config/` directory.
