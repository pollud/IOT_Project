# MQTT API Documentation

## System Level Topics

### `system/alerts`
- **Description**: System-wide safety or error alerts.
- **Publisher**: `safety_monitor`
- **Subscriber**: `node_red`, `telegram_bot`
- **Payload**:
  ```json
  {
    "type": "alert_type",
    "message": "Human-readable message"
  }
  ```

## Room Level Topics

### `room/<room_id>/environment`
- **Description**: Environment telemetry (temperature, humidity).
- **Publisher**: `room_connector`
- **Subscriber**: `safety_monitor`, `timeseries_adapter`, `node_red`
- **Payload**:
  ```json
  {
    "temperature": 22.5,
    "humidity": 45.0
  }
  ```

### `room/<room_id>/badge/<badge_id>/position`
- **Description**: Player location tracking.
- **Publisher**: `badge_connector`
- **Subscriber**: `room_control`
- **Payload**:
  ```json
  {
    "zone": "zone_name"
  }
  ```

### `room/<room_id>/prop/<prop_id>/event`
- **Description**: Interaction event with a physical prop.
- **Publisher**: `prop_connector`
- **Subscriber**: `room_control`
- **Payload**:
  ```json
  {
    "action": "action_name"
  }
  ```

### `room/<room_id>/status`
- **Description**: Current state of the Room Control FSM.
- **Publisher**: `room_control`
- **Subscriber**: `telegram_bot`, `timeseries_adapter`
- **Payload**:
  ```json
  {
    "room_id": "room1",
    "current_state": "playing"
  }
  ```

## Command Topics

### `command/room`
- **Description**: Commands sent to a specific room to manually override state or hardware.
- **Publisher**: `node_red`, `telegram_bot`
- **Subscriber**: `room_control`, `room_connector`
- **Payload**:
  ```json
  {
    "room_id": "room1",
    "command": "unlockDoor"
  }
  ```

## Game / Session Topics

### `game/<room_id>/session/started`
- **Description**: Signals the start of an escape room session.
- **Publisher**: `room_control`
- **Subscriber**: `timeseries_adapter`
- **Payload**:
  ```json
  {
    "room_id": "room1"
  }
  ```

### `game/<room_id>/session/ended`
- **Description**: Signals the end of a session, triggering analytics.
- **Publisher**: `room_control`
- **Subscriber**: `timeseries_adapter`, `analytics`
- **Payload**:
  ```json
  {
    "room_id": "room1",
    "duration": 3600,
    "status": "won|lost"
  }
  ```

## Configuration Topics

### `catalog/<room_id>/config-update`
- **Description**: Hot-reloads room strategies.
- **Publisher**: `catalog`
- **Subscriber**: `room_control`
- **Payload**: Full JSON strategy document.
