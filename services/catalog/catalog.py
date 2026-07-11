import cherrypy
import paho.mqtt.client as mqtt
import threading
import time
import os
import glob
import json
from shared.models import ConfigUpdateEvent
from shared.topics import build_topic
from shared.utils import to_json
from shared.constants import DEFAULT_PORT

class GameCatalog:
    def __init__(self):
        self.services = []
        self.devices = []
        self.rooms = ["room1"]
        
        # Connect to Mosquitto. In docker-compose, hostname is "mosquitto"
        # However, it might be running locally. Let's use env var or default.
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        
        self.mqtt_client = mqtt.Client()
        # Retry logic for MQTT connection
        connected = False
        while not connected:
            try:
                self.mqtt_client.connect(broker, DEFAULT_PORT, 60)
                connected = True
            except Exception as e:
                print(f"Waiting for MQTT broker at {broker}... ({e})")
                time.sleep(2)
                
        self.mqtt_client.loop_start()

        # File watcher thread
        self.last_mtime = {}
        t = threading.Thread(target=self._watch_configs, daemon=True)
        t.start()

    def _watch_configs(self):
        while True:
            for filepath in glob.glob("config/strategy_*.json"):
                try:
                    mtime = os.path.getmtime(filepath)
                except FileNotFoundError:
                    continue
                    
                if filepath not in self.last_mtime:
                    self.last_mtime[filepath] = mtime
                elif mtime > self.last_mtime[filepath]:
                    self.last_mtime[filepath] = mtime
                    room_id = os.path.basename(filepath).replace("strategy_", "").replace(".json", "")
                    
                    try:
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                        version = data.get("version", "unknown")
                        
                        event = ConfigUpdateEvent(room_id=room_id, version=version)
                        topic = build_topic(room_id, "catalog", "config-update")
                        self.mqtt_client.publish(topic, to_json(event), retain=True)
                        print(f"Published config update for {room_id} version {version}")
                    except Exception as e:
                        print(f"Error publishing config update: {e}")
            time.sleep(0.5)

catalog = GameCatalog()

class ConfigRoute(object):
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def default(self, room):
        filepath = f"config/strategy_{room}.json"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        raise cherrypy.HTTPError(404)

class Root(object):
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def services(self):
        return {"services": catalog.services}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def devices(self):
        return {"devices": catalog.devices}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def rooms(self):
        return {"rooms": catalog.rooms}
        
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def register(self):
        data = cherrypy.request.json
        if data.get("type") == "device":
            catalog.devices.append(data)
        elif data.get("type") == "service":
            catalog.services.append(data)
        return {"status": "registered"}

if __name__ == '__main__':
    root = Root()
    root.config = ConfigRoute()

    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8080,
    })
    cherrypy.quickstart(root)
