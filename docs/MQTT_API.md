# MQTT API Documentation

## System Level Topics

### `system/alerts`
- **Description**: System-wide safety or error alerts.
- **Publisher**: `safety_monitor`
- **Subscriber**: `web_dashboard`, `timeseries_adapter`
- **Payload**:
  ```json
  {
    "alert_type": "fall",
    "message": "Fall detected for b1",
    "source": "room1"
  }
  ```

## Room Level Topics

### `room/<room_id>/environment`
- **Description**: Environment telemetry (temperature, humidity).
- **Publisher**: `room_connector`
- **Subscriber**: `safety_monitor`, `timeseries_adapter`, `web_dashboard`
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
- **Subscriber**: `timeseries_adapter`, `web_dashboard`
- **Payload**:
  ```json
  {
    "badge_id": "b1",
    "x": 3.5,
    "y": 7.2
  }
  ```

### `room/<room_id>/prop/<prop_id>/event`
- **Description**: Interaction event with a physical prop.
- **Publisher**: `prop_connector`, `web_dashboard`
- **Subscriber**: `room_control`, `timeseries_adapter`
- **Payload**:
  ```json
  {
    "prop_id": "prop1",
    "interaction_type": "button",
    "value": "pressed"
  }
  ```

### `room/<room_id>/status`
- **Description**: Current state of the Room Control FSM.
- **Publisher**: `room_control`
- **Subscriber**: `web_dashboard`, `timeseries_adapter`
- **Payload**:
  ```json
  {
    "room_id": "room1",
    "current_state": "playing"
  }
  ```

## Command Topics

### `command/room/<room_id>`
- **Description**: Commands sent to a specific room to manually override state or hardware.
- **Publisher**: `web_dashboard`
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
