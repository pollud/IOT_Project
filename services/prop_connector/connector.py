import cherrypy
import os
import time
import threading
import json
from shared.mqtt import MQTTClient
from shared.models import PropEvent, HeartbeatEvent
from shared.topics import build_topic

class PropConnector:
    def __init__(self, room_id, prop_id):
        self.room_id = room_id
        self.prop_id = prop_id
        
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id=f"prop_{self.prop_id}",
            broker=broker,
            heartbeat_topic=build_topic(self.room_id, "prop", "heartbeat", self.prop_id),
            heartbeat_interval=5,
            heartbeat_payload=HeartbeatEvent(device_id=f"prop_{self.prop_id}", status="ok")
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
                print(e)
                time.sleep(2)
                
        # Simulate health messages
        t = threading.Thread(target=self.publish_health, daemon=True)
        t.start()
        
    def publish_health(self):
        while True:
            self.mqtt.publish(build_topic(self.room_id, "prop", "health", self.prop_id), {"status": "ok", "battery": 95.0})
            time.sleep(2)
            
    def trigger(self, interaction_type, value):
        event = PropEvent(prop_id=self.prop_id, interaction_type=interaction_type, value=value)
        self.mqtt.publish(build_topic(self.room_id, "prop", "interaction", self.prop_id), event)

class PropRoute:
    def __init__(self, connector):
        self.connector = connector
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def trigger_button(self):
        self.connector.trigger("button", "pressed")
        return {"status": "ok"}
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def trigger_rfid(self):
        data = cherrypy.request.json if cherrypy.request.headers.get("Content-Type") == "application/json" else {}
        uid = data.get("uid", "12345") if data else "12345"
        self.connector.trigger("rfid", uid)
        return {"status": "ok"}
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def trigger_cap(self):
        self.connector.trigger("capacitive", "touched")
        return {"status": "ok"}

if __name__ == "__main__":
    room_id = os.getenv("ROOM_ID", "room1")
    prop_id = os.getenv("PROP_ID", "prop1")
    connector = PropConnector(room_id, prop_id)
    
    root = PropRoute(connector)
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8083,
    })
    cherrypy.quickstart(root)
