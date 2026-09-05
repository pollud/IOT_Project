"""Actuator action executor used by the room FSM."""

from __future__ import annotations

from shared.models import RoomCommand
from shared.topics import room_command


class ActionExecutor:
    def __init__(self, mqtt_client, room_id: str) -> None:
        self.mqtt = mqtt_client
        self.room_id = room_id

    def execute(self, action: dict) -> str | None:
        """Execute an FSM action and return semantic status actions."""
        name = action["action"]
        if name == "publishStatus":
            return str(action["status"])
        if name == "unlockDoor":
            command, parameters = "unlock", {"target": action.get("target", "main_door")}
        elif name == "lockDoor":
            command, parameters = "lock", {"target": action.get("target", "main_door")}
        elif name == "playAudio":
            command, parameters = "play_audio", {"track": action["track"]}
        elif name == "setLights":
            command, parameters = "set_lights", {"color": action["color"]}
        else:
            raise ValueError(f"Unsupported FSM action: {name}")
        self.mqtt.publish(
            room_command(self.room_id),
            RoomCommand(
                room_id=self.room_id,
                command=command,
                parameters=parameters,
                issued_by=f"room_control_{self.room_id}",
            ),
            qos=1,
        )
        return None
