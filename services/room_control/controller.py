import os
import time
import json
from shared.mqtt import MQTTClient
from shared.topics import build_topic
from fsm import RoomFSM
from loader import load_strategy_from_file

class RoomController:
    def __init__(self, room_id):
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
                time.sleep(1)
                if self.mqtt.connected:
                    connected = True
                else:
                    self.mqtt.stop()
                    time.sleep(1)
            except Exception as e:
                print(e)
                time.sleep(2)
                
        strategy = load_strategy_from_file(f"/app/config/strategy_{self.room_id}.json")
        self.fsm = RoomFSM(self.room_id, strategy, self.mqtt)
        
        self.mqtt.subscribe(build_topic(self.room_id, "prop", "interaction", "+"))
        self.mqtt.subscribe(build_topic(self.room_id, "catalog", "config-update"))
        
    def on_message(self, topic, payload):
        if "interaction" in topic:
            data = json.loads(payload)
            prop_id = data.get("prop_id")
            interaction_type = data.get("interaction_type")
            val = data.get("value")
            
            self.fsm.event_transition("PropEvent", prop_id, interaction_type, val)
            
        elif "config-update" in topic:
            print(f"[{self.room_id}] Received config update!")
            strategy = load_strategy_from_file(f"/app/config/strategy_{self.room_id}.json")
            self.fsm.load_strategy(strategy)

if __name__ == "__main__":
    room_id = os.getenv("ROOM_ID", "room1")
    controller = RoomController(room_id)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.mqtt.stop()
