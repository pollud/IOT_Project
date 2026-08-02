import os
import time
import json
from shared.mqtt import MQTTClient
from shared.models import RoomCommand, AlertEvent
from shared.topics import build_topic

class SafetyMonitor:
    def __init__(self):
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id="safety_monitor",
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
                
        self.mqtt.subscribe("game/+/badge/+/safety")
        self.mqtt.subscribe("room/+/environment")
        
    def on_message(self, topic, payload):
        if "safety" in topic:
            data = json.loads(payload)
            if data.get("fall_detected"):
                parts = topic.split("/")
                room_id = parts[1]
                badge_id = parts[3]
                
                print(f"FALL DETECTED in {room_id} for {badge_id}")
                
                # 1. Command emergency
                cmd = RoomCommand(command="emergency_unlock")
                self.mqtt.publish(build_topic(None, "command", "emergency"), cmd, qos=1)
                
                # 2. System Alert
                alert = AlertEvent(alert_type="fall", message=f"Fall detected for {badge_id}", source=room_id)
                self.mqtt.publish(build_topic(None, "system", "alerts"), alert, qos=1)
                
        elif "environment" in topic:
            data = json.loads(payload)
            if data.get("temperature", 0) > 40.0:
                parts = topic.split("/")
                room_id = parts[1]
                alert = AlertEvent(alert_type="temperature", message="High temperature", source=room_id)
                self.mqtt.publish(build_topic(None, "system", "alerts"), alert, qos=1)

if __name__ == "__main__":
    monitor = SafetyMonitor()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.mqtt.stop()
