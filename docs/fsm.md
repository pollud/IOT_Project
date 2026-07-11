# Room Control FSM

## Concepts
The FSM defines the sequence of states, required transitions, and actions to execute.

## `room_strategy.json` Schema

```json
{
  "room_id": "string",
  "version": "string",
  "initial_state": "locked",
  "states": {
    "locked": {
      "transitions": [
        {
          "trigger": "event",
          "event_type": "PropEvent",
          "prop_id": "rfid_reader_1",
          "condition": "payload.value == '12345'",
          "target_state": "unlocked"
        },
        {
          "trigger": "time",
          "duration_seconds": 300,
          "target_state": "hint_needed"
        }
      ],
      "on_enter": [
        {"action": "setLights", "color": "red"}
      ]
    },
    "unlocked": {
      "on_enter": [
        {"action": "unlockDoor"},
        {"action": "playAudio", "track": "success.mp3"},
        {"action": "publishStatus", "status": "completed"}
      ]
    },
    "hint_needed": {
      "on_enter": [
        {"action": "playAudio", "track": "hint1.mp3"}
      ],
      "transitions": [
        {
          "trigger": "time",
          "duration_seconds": 10,
          "target_state": "locked"
        }
      ]
    }
  }
}
```

## Time-based Transitions
When entering a state, the FSM schedules any `time` triggers with the Scheduler component. If a transition out of the state occurs before the time duration is reached, the pending timer must be cancelled.
