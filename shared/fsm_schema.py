"""JSON Schema definitions and validation logic for Room Finite State Machine (FSM) strategies."""

import jsonschema

#: JSON schema defining the required structure for room strategy configurations.
RoomStrategySchema = {
    "type": "object",
    "properties": {
        "room_id": {"type": "string"},
        "version": {"type": "string"},
        "initial_state": {"type": "string"},
        "states": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "transitions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "trigger": {"type": "string", "enum": ["event", "time"]},
                                "target_state": {"type": "string"}
                            },
                            "required": ["trigger", "target_state"]
                        }
                    },
                    "on_enter": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string"}
                            },
                            "required": ["action"]
                        }
                    }
                }
            }
        }
    },
    "required": ["room_id", "version", "initial_state", "states"]
}

def validate_strategy(strategy: dict) -> None:
    """Validate a room strategy dictionary against the RoomStrategySchema.

    Args:
        strategy (dict): Room strategy configuration dictionary.

    Raises:
        jsonschema.exceptions.ValidationError: If strategy fails schema validation.
    """
    jsonschema.validate(instance=strategy, schema=RoomStrategySchema)

