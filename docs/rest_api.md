# REST APIs

## Game Catalog (`services/catalog`)
- `GET /services`: List registered services and their statuses.
- `GET /devices`: List registered devices (badges, props).
- `GET /rooms`: List configured rooms.
- `GET /config/<room>`: Get the current `room_strategy.json` for a specific room.
- `POST /register`: Register a new device or service.

## Room Connector (`services/room_connector`)
- `GET /calibration`: Retrieve environment sensor calibration data.
- `GET /actuator/health`: Check status of connected actuators.

## TimeSeriesDB Adapter (`services/timeseries_adapter`)
- `GET /events?room=&from=&to=&type=`: Fetch historical events for a given room, time range, and event type.

## Analytics Engine (`services/analytics`)
- (No exposed REST API; operates via MQTT subscriptions and queries TimeSeriesDB over REST).

## ThingSpeak Adapter (`services/thingspeak_adapter`)
- `GET /history`: Expose filtered metrics for Node-RED to render without touching the ThingSpeak cloud directly.
