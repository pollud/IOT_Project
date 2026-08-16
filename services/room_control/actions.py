"""Action execution module for room control FSM state transitions."""

from shared.models import RoomCommand, GameStatus, SessionEndedEvent
from shared.topics import build_topic

class ActionExecutor:
    """Executes actions defined in room FSM strategy state on_enter blocks by publishing MQTT commands and status updates."""

    def __init__(self, mqtt_client, room_id: str):
        """Initialize ActionExecutor.

        Args:
            mqtt_client: Instance of MQTTClient for message publishing.
            room_id (str): Identifier of the target room.
        """
        self.mqtt = mqtt_client
        self.room_id = room_id
        
    def execute(self, action_dict: dict):
        """Parse action definition dictionary and publish corresponding MQTT command or event.

        Args:
            action_dict (dict): Dictionary specifying action type and parameters (e.g. unlockDoor, playAudio, setLights, publishStatus).
        """
        action = action_dict.get("action")
        if action == "unlockDoor":
            cmd = RoomCommand(command="unlock", target=action_dict.get("target"))
            self.mqtt.publish(build_topic(self.room_id, "room", "command"), cmd, qos=2)
        elif action == "playAudio":
            cmd = RoomCommand(command="play_audio", payload={"track": action_dict.get("track")})
            self.mqtt.publish(build_topic(self.room_id, "room", "command"), cmd, qos=2)
        elif action == "setLights":
            cmd = RoomCommand(command="set_lights", payload={"color": action_dict.get("color")})
            self.mqtt.publish(build_topic(self.room_id, "room", "command"), cmd, qos=2)
        elif action == "publishStatus":
            status = action_dict.get("status")
            cmd = GameStatus(status=status, time_elapsed=0)
            self.mqtt.publish(build_topic(self.room_id, "game", "status"), cmd, qos=1, retain=True)
            if status == "completed":
                ended = SessionEndedEvent(room_id=self.room_id, duration=3600, success=True)
                self.mqtt.publish(build_topic(self.room_id, "session", "ended"), ended, qos=1)

