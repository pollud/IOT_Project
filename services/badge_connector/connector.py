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
        self.total_badges = 80
        self.active_badges = 80
        
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id="badge_connector",
            broker=broker,
            heartbeat_topic="status/badge_connector",
            heartbeat_interval=5,
            heartbeat_payload={
                "service": "badge_connector",
                "status": "online",
                "badges_active": self.active_badges,
                "badges_total": self.total_badges,
                "timestamp": time.time()
            }
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
        while True:
            self.mqtt.publish("status/badge_connector", {
                "service": "badge_connector",
                "status": "online",
                "badges_active": self.active_badges,
                "badges_total": self.total_badges,
                "timestamp": time.time()
            }, qos=1, retain=True)
            time.sleep(5)
            
    def force_fall(self):
        fall = BadgeSafetyEvent(badge_id=self.badge_id, fall_detected=True)
        self.mqtt.publish(build_topic(self.room_id, "badge", "safety", self.badge_id), fall, qos=1)

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
