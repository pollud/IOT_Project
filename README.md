# IoT Escape Room Platform — Game Master Command Center

A robust, microservices-based, event-driven IoT architecture for orchestrating smart escape rooms with automated state machines, sensor telemetry, safety monitoring, and a unified Web Command Center.

## Architecture

The system operates via an MQTT message bus connecting independent containerized microservices, orchestrated from a single Web Dashboard with real-time Server-Sent Events (SSE).

```mermaid
graph TD;
    Mosquitto((Mosquitto MQTT Broker :1883))
    
    RoomConnector["Room Connector (:8081)<br/>(Env Sensors & Actuator Relays)"] -->|room/{id}/environment| Mosquitto
    BadgeConnector["Badge Connector (:8082)<br/>(Player Position, Fall, Battery)"] -->|game/{id}/badge/{id}/...| Mosquitto
    PropConnector["Prop Connector (:8083)<br/>(RFID, Button, Keypads)"] -->|game/{id}/prop/{id}/interaction| Mosquitto
    
    Mosquitto -->|interactions, commands| RoomControl["Room Control FSM<br/>(State Engine & Timers)"]
    RoomControl -->|room/{id}/status, command| Mosquitto
    
    Mosquitto -->|badge safety, environment| SafetyMonitor["Safety Monitor<br/>(Emergency Fail-Safe)"]
    SafetyMonitor -->|command/emergency, system/alerts| Mosquitto
    
    Catalog["Game Catalog REST (:8080)<br/>(Registry & Config Watcher)"] -->|catalog/{id}/config-update| Mosquitto
    
    Mosquitto -->|all telemetry namespaces| TimeSeries["TimeSeries DB Adapter<br/>(Batch Ingestion Queue)"]
    TimeSeries --> SQLite[(SQLite DB: events.db)]
    
    Analytics["Analytics Engine REST (:8084)<br/>(KPIs, Heatmaps & Reports)"] --> SQLite
    
    Mosquitto <-->|telemetry & commands| WebDashboard["Web Dashboard Backend (:8087)<br/>(SSE Streaming & REST Proxy)"]
    Catalog -->|REST| WebDashboard
    Analytics -->|REST| WebDashboard
    WebDashboard <-->|SSE & REST| WebUI["Web UI Command Center<br/>(Live Matrix, Controls, Heatmaps)"]
```

## Microservices Breakdown

| Microservice | Port | Primary Protocol | Role |
| :--- | :--- | :--- | :--- |
| **Mosquitto** | `1883` | MQTT | Central asynchronous event bus |
| **Catalog** | `8080` | REST / MQTT | Service/device registry & strategy hot-reloader |
| **Room Connector** | `8081` | MQTT / REST | Physical room sensors & actuator relays |
| **Badge Connector** | `8082` | MQTT / REST | Player badge positioning, battery & fall detection |
| **Prop Connector** | `8083` | MQTT / REST | Interactive puzzle prop sensors (RFID, buttons) |
| **Room Control FSM** | *Internal* | MQTT | Autonomous puzzle state machine & scheduler |
| **Safety Monitor** | *Internal* | MQTT | High-priority safety fail-safe & emergency unlock |
| **TimeSeries Adapter**| *Internal* | MQTT / SQLite | High-throughput batch telemetry recorder |
| **Analytics Engine** | `8084` | REST / SQLite | Performance stats, chokepoints & spatial heatmaps |
| **Web Dashboard** | `8087` | HTTP REST / SSE | **Game Master Command Center UI & API Gateway** |

## Running the Stack

Requires Docker and docker-compose.

```bash
docker-compose up -d --build
```

Access the Game Master Command Center at:
👉 **`http://localhost:8087`**

## Verification & Testing

The project includes an automated test suite verifying every phase of the project implementation.
Run end-to-end multi-room simulation:
```bash
python3 tests/phase_gates/verify_phase_15.py
```
