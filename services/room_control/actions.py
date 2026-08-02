from shared.models import RoomCommand, GameStatus, SessionEndedEvent
from shared.topics import build_topic

class ActionExecutor:
    def __init__(self, mqtt_client, room_id):
        self.mqtt = mqtt_client
        self.room_id = room_id
        
    def execute(self, action_dict):
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
