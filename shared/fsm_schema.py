# jsonschema definition for room_strategy.json
import jsonschema

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

def validate_strategy(strategy: dict):
    jsonschema.validate(instance=strategy, schema=RoomStrategySchema)
