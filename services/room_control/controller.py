"""Room controller service managing room FSM lifecycle, MQTT topics, and strategy updates."""

import os
import time
import json
from shared.mqtt import MQTTClient
from shared.topics import build_topic
from fsm import RoomFSM
from loader import load_strategy_from_file

#: List of all supported room IDs in the game center.
ALL_KNOWN_ROOMS = [
    "room1",
    "room2",
    "room_cyberpunk",
    "room_matrix",
    "room_alien",
    "room_dungeon",
    "room_atlantis",
    "room_tomb",
    "room_haunted",
    "room_asylum",
    "room_sherlock",
    "room_arcade"
]

class RoomController:
    """Controller connecting MQTT topic subscriptions for a room to its underlying RoomFSM engine."""

    def __init__(self, room_id: str):
        """Initialize RoomController for room_id, setup MQTT client, load strategy, and subscribe to topics.

        Args:
            room_id (str): Target room identifier.
        """
        self.room_id = room_id
        
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id=f"room_control_{self.room_id}",
            broker=broker
        )
        self.mqtt.on_message_callback = self.on_message
        
        connected = False
        while not connected:
            try:
                self.mqtt.start()
                time.sleep(0.5)
                if self.mqtt.connected:
                    connected = True
                else:
                    self.mqtt.stop()
                    time.sleep(0.5)
            except Exception as e:
                print(f"[{self.room_id}] Waiting for mosquitto... {e}")
                time.sleep(1)
                
        strategy_file = f"/app/config/strategy_{self.room_id}.json"
        if not os.path.exists(strategy_file):
            # Fallback to room1 strategy if file does not exist
            strategy_file = "/app/config/strategy_room1.json"

        strategy = load_strategy_from_file(strategy_file)
        self.fsm = RoomFSM(self.room_id, strategy, self.mqtt)
        
        self.mqtt.subscribe(build_topic(self.room_id, "prop", "interaction", "+"))
        self.mqtt.subscribe(build_topic(self.room_id, "catalog", "config-update"))
        self.mqtt.subscribe(build_topic(self.room_id, "room", "command"))
        self.mqtt.subscribe(f"command/room/{self.room_id}")
        self.mqtt.subscribe(f"room/{self.room_id}/status")
        
    def on_message(self, topic: str, payload):
        """Handle incoming MQTT messages for state recovery, room commands, prop interactions, and config updates.

        Args:
            topic (str): MQTT topic string.
            payload (str or dict): Message payload.
        """
        try:
            data = json.loads(payload) if isinstance(payload, str) or isinstance(payload, bytes) else payload
        except Exception:
            data = {}

        if f"room/{self.room_id}/status" in topic:
            retained_state = data.get("current_state") if isinstance(data, dict) else None
            if retained_state:
                self.fsm.restore_state(retained_state)

        elif "command" in topic:
            cmd = data.get("command") if isinstance(data, dict) else None
            if cmd == "reset":
                print(f"[{self.room_id}] Resetting FSM...")
                self.fsm.reset_room()
            elif cmd == "unlockDoor":
                print(f"[{self.room_id}] Forcing unlock...")
                self.fsm.force_unlock()

        elif "interaction" in topic:
            if isinstance(data, dict):
                prop_id = data.get("prop_id")
                interaction_type = data.get("interaction_type")
                val = data.get("value")
                self.fsm.event_transition("PropEvent", prop_id, interaction_type, val)
            
        elif "config-update" in topic:
            print(f"[{self.room_id}] Received config update!")
            strategy_file = f"/app/config/strategy_{self.room_id}.json"
            if not os.path.exists(strategy_file):
                strategy_file = "/app/config/strategy_room1.json"
            strategy = load_strategy_from_file(strategy_file)
            self.fsm.load_strategy(strategy)

if __name__ == "__main__":
    env_room = os.getenv("ROOM_ID", "ALL")
    
    if env_room == "ALL" or env_room == "all":
        target_rooms = ALL_KNOWN_ROOMS
    else:
        target_rooms = [r.strip() for r in env_room.split(",") if r.strip()]
        
    controllers = []
    print(f"🚀 Initializing Room Controllers for: {target_rooms}")
    for r_id in target_rooms:
        ctrl = RoomController(r_id)
        controllers.append(ctrl)
        
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for ctrl in controllers:
            ctrl.mqtt.stop()

