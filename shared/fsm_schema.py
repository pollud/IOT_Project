"""Structural and semantic validation of room FSM strategies."""

from __future__ import annotations

import re

import jsonschema

from shared.constants import ROOM_ID_PATTERN

ALLOWED_ACTIONS = {"unlockDoor", "lockDoor", "playAudio", "setLights", "publishStatus"}

RoomStrategySchema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "room_id": {"type": "string", "pattern": ROOM_ID_PATTERN},
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "initial_state": {"type": "string", "minLength": 1},
        "states": {
            "type": "object",
            "minProperties": 2,
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "is_terminal": {"type": "boolean"},
                    "on_enter": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["action"],
                            "properties": {"action": {"enum": sorted(ALLOWED_ACTIONS)}},
                            "additionalProperties": True,
                        },
                    },
                    "transitions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["trigger", "target_state"],
                            "properties": {
                                "trigger": {"enum": ["event", "time"]},
                                "target_state": {"type": "string", "minLength": 1},
                                "duration_seconds": {"type": "number", "exclusiveMinimum": 0},
                                "event_type": {"const": "PropEvent"},
                                "prop_id": {"type": "string", "pattern": ROOM_ID_PATTERN},
                                "interaction_type": {"type": "string", "minLength": 1},
                                "value": {"type": ["string", "number", "boolean"]},
                            },
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["on_enter", "transitions"],
            },
        },
    },
    "required": ["room_id", "name", "version", "initial_state", "states"],
}


def validate_strategy(strategy: dict) -> None:
    jsonschema.Draft7Validator(RoomStrategySchema).validate(strategy)
    states = strategy["states"]
    if strategy["initial_state"] not in states:
        raise ValueError("initial_state is not defined in states")
    if not any(definition.get("is_terminal") for definition in states.values()):
        raise ValueError("At least one terminal state is required")

    for state_name, definition in states.items():
        if not re.fullmatch(ROOM_ID_PATTERN, state_name):
            raise ValueError(f"Invalid state identifier: {state_name}")
        for transition in definition["transitions"]:
            if transition["target_state"] not in states:
                raise ValueError(
                    f"State {state_name} targets unknown state {transition['target_state']}"
                )
            if transition["trigger"] == "time" and "duration_seconds" not in transition:
                raise ValueError(f"Timed transition in {state_name} needs duration_seconds")
            if transition["trigger"] == "event":
                required = {"event_type", "prop_id", "interaction_type", "value"}
                missing = required - transition.keys()
                if missing:
                    raise ValueError(f"Event transition in {state_name} misses {sorted(missing)}")
        for action in definition["on_enter"]:
            name = action["action"]
            requirements = {
                "playAudio": "track",
                "setLights": "color",
                "publishStatus": "status",
            }
            required_parameter = requirements.get(name)
            if required_parameter and required_parameter not in action:
                raise ValueError(f"Action {name} in {state_name} needs {required_parameter}")

