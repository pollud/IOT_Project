import cherrypy
import os
import time
import threading
import json
from shared.mqtt import MQTTClient
from shared.models import EnvironmentEvent, HeartbeatEvent
from shared.topics import build_topic
import random

class ActuatorRoute:
    def __init__(self, parent):
        self.parent = parent
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {"status": "ok", "logs": self.parent.actuator_log}

class RoomConnector:
    def __init__(self, room_id):
        self.room_id = room_id
        
        # simulated actuators log
        self.actuator_log = []
        
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id=f"room_connector_{self.room_id}",
            broker=broker,
            heartbeat_topic=build_topic(self.room_id, "room", "heartbeat"),
            heartbeat_interval=5,
            heartbeat_payload=HeartbeatEvent(device_id=f"room_{self.room_id}", status="ok")
        )
        self.mqtt.on_message_callback = self.on_mqtt_message
        
        # Connect with retry
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
            
        # Subscriptions
        self.mqtt.subscribe(build_topic(self.room_id, "room", "command"))
        self.mqtt.subscribe(build_topic(None, "command", "emergency"))
        
        # Environment publish loop
        t = threading.Thread(target=self.publish_environment, daemon=True)
        t.start()
        
        self.actuator = ActuatorRoute(self)
        
    def on_mqtt_message(self, topic, payload):
        if "emergency" in topic:
            print(f"[{self.room_id}] EMERGENCY OVERRIDE RECEIVED: {payload}")
            self.actuator_log.append({"type": "emergency", "payload": payload})
        else:
            print(f"[{self.room_id}] ROOM COMMAND RECEIVED: {payload}")
            self.actuator_log.append({"type": "room_command", "payload": payload})
            
    def publish_environment(self):
        while True:
            try:
                env = EnvironmentEvent(temperature=22.0 + random.random(), humidity=45.0 + random.random())
                topic = build_topic(self.room_id, "room", "environment")
                self.mqtt.publish(topic, env, qos=0)
            except Exception as e:
                print(f"Error publishing environment: {e}")
            time.sleep(2)
            
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def calibration(self):
        return {"temp_offset": -0.5, "hum_offset": 2.0}

if __name__ == "__main__":
    room_id = os.getenv("ROOM_ID", "room1")
    connector = RoomConnector(room_id)
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8081,
    })
    cherrypy.quickstart(connector)
