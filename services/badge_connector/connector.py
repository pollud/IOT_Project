import cherrypy
import os
import time
import threading
import random
from shared.mqtt import MQTTClient
from shared.models import BadgePositionEvent, BadgeSafetyEvent, BatteryEvent, HeartbeatEvent
from shared.topics import build_topic

class BadgeConnector:
    def __init__(self, room_id, badge_id):
        self.room_id = room_id
        self.badge_id = badge_id
        
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id=f"badge_{self.badge_id}",
            broker=broker,
            heartbeat_topic=build_topic(self.room_id, "badge", "heartbeat", self.badge_id),
            heartbeat_interval=5,
            heartbeat_payload=HeartbeatEvent(device_id=f"badge_{self.badge_id}", status="ok")
        )
        
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
                print(f"Waiting for mosquitto... {e}")
                time.sleep(2)
                
        t = threading.Thread(target=self.simulation_loop, daemon=True)
        t.start()
        
    def simulation_loop(self):
        battery = 100.0
        while True:
            # Position
            pos = BadgePositionEvent(badge_id=self.badge_id, x=random.uniform(0, 10), y=random.uniform(0, 10))
            self.mqtt.publish(build_topic(self.room_id, "badge", "position", self.badge_id), pos)
            
            # Battery
            battery -= 0.1
            bat = BatteryEvent(badge_id=self.badge_id, battery_level=battery)
            self.mqtt.publish(build_topic(self.room_id, "badge", "battery", self.badge_id), bat)
            
            time.sleep(2)
            
    def force_fall(self):
        fall = BadgeSafetyEvent(badge_id=self.badge_id, fall_detected=True)
        self.mqtt.publish(build_topic(self.room_id, "badge", "safety", self.badge_id), fall)

class BadgeRoute:
    def __init__(self, connector):
        self.connector = connector
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def force_fall(self):
        self.connector.force_fall()
        return {"status": "fall forced"}

if __name__ == "__main__":
    room_id = os.getenv("ROOM_ID", "room1")
    badge_id = os.getenv("BADGE_ID", "b1")
    connector = BadgeConnector(room_id, badge_id)
    
    root = BadgeRoute(connector)
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8082,
    })
    cherrypy.quickstart(root)
