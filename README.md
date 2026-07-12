# IoT Escape Room Platform

A robust, microservices-based, event-driven architecture for running real-world or simulated Escape Rooms.

## Architecture

The system operates via an MQTT message bus connecting independent containerized microservices.

```mermaid
graph TD;
    Mosquitto((Mosquitto MQTT))
    
    RoomConnector[Room Connector] -->|environment| Mosquitto
    BadgeConnector[Badge Connector] -->|position| Mosquitto
    PropConnector[Prop Connector] -->|event| Mosquitto
    
    Mosquitto -->|events| RoomControl[Room Control FSM]
    RoomControl -->|status, session| Mosquitto
    
    Mosquitto -->|environment| SafetyMonitor[Safety Monitor]
    SafetyMonitor -->|system/alerts| Mosquitto
    
    Catalog[Game Catalog REST] -->|config-update| Mosquitto
    
    Mosquitto -->|all telemetry| TimeSeries[Time Series Adapter]
    TimeSeries --> SQLite[(SQLite DB)]
    
    Mosquitto -->|session/ended| Analytics[Analytics Engine REST]
    Analytics --> SQLite
    
    Mosquitto --> ThingSpeak[ThingSpeak Adapter]
    
    Mosquitto --> NodeRED[Node-RED Dashboard]
    NodeRED -->|command/room| Mosquitto
    
    Mosquitto --> Telegram[Telegram Bot]
    Telegram -->|command/room| Mosquitto
```

## Running the Stack

Requires Docker and docker-compose.

```bash
docker-compose up -d --build
```

This will launch all services including:
- Mosquitto Broker (`:1883`)
- Game Catalog (`:8080`)
- Node-RED Dashboard (`:1880`)
- Analytics (`:8084`)

## Verification

The project includes an automated test suite verifying every phase of the project implementation.
Run individual phase verifications:
```bash
python3 tests/phase_gates/verify_phase_15.py
```
