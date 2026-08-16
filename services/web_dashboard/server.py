"""Web Dashboard backend server bridging MQTT telemetry and REST APIs to the frontend via Server-Sent Events (SSE) and HTTP endpoints."""

import cherrypy
import os
import time
import json
import threading
import requests
import queue
from shared.mqtt import MQTTClient

#: Set of known room IDs monitored by the web dashboard.
KNOWN_ROOMS = {
    "room_cyberpunk",
    "room_matrix",
    "room_alien",
    "room_dungeon",
    "room_atlantis",
    "room_tomb",
    "room_haunted",
    "room_asylum",
    "room_sherlock",
    "room_arcade",
    "room1",
    "room2"
}

class WebDashboardAPI:
    """Backend controller bridging live MQTT events to frontend web clients via Server-Sent Events (SSE) and handling command dispatch."""

    def __init__(self):
        """Initialize WebDashboardAPI, setup MQTT connection, and launch subscription thread."""
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id="web_dashboard",
            broker=broker
        )
        self.cache = {
            "rooms": {},
            "presence": {}
        }
        self.listeners = set()
        self.listeners_lock = threading.Lock()
        self.mqtt.on_message_callback = self.on_message
        
        t = threading.Thread(target=self.run_mqtt, daemon=True)
        t.start()
        
    def run_mqtt(self):
        """Background thread connecting to MQTT broker and subscribing to status, telemetry, alert, and presence topics."""
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
            except Exception:
                time.sleep(2)
        self.mqtt.subscribe("room/+/status")
        self.mqtt.subscribe("game/+/status")
        self.mqtt.subscribe("catalog/+/config-update")
        self.mqtt.subscribe("room/+/environment")
        self.mqtt.subscribe("system/alerts")
        self.mqtt.subscribe("status/+")
        
    def on_message(self, topic: str, payload):
        """Handle incoming MQTT messages, update local state cache, and broadcast events to all connected SSE streaming queues.

        Args:
            topic (str): MQTT topic string.
            payload (Any): Message payload string or dict.
        """
        try:
            data = json.loads(payload)
            if topic.startswith("status/"):
                service_id = topic.split("/")[1]
                if isinstance(data, dict):
                    self.cache["presence"][service_id] = data
            elif "status" in topic or "config-update" in topic:
                parts = topic.split("/")
                if len(parts) >= 2:
                    room_id = parts[1]
                    if room_id in KNOWN_ROOMS or room_id.startswith("room"):
                        if room_id not in self.cache["rooms"]:
                            self.cache["rooms"][room_id] = {"room_id": room_id, "current_state": "entrance"}
                        if isinstance(data, dict):
                            self.cache["rooms"][room_id].update(data)
        except Exception:
            data = payload

        event_msg = json.dumps({"topic": topic, "data": data})
        with self.listeners_lock:
            for q in list(self.listeners):
                try:
                    q.put_nowait(event_msg)
                except Exception:
                    pass

    @cherrypy.expose
    def stream(self):
        """GET /api/stream endpoint delivering live real-time events to frontend web clients via Server-Sent Events (SSE)."""
        cherrypy.response.headers['Content-Type'] = 'text/event-stream'
        cherrypy.response.headers['Cache-Control'] = 'no-cache'
        cherrypy.response.headers['Connection'] = 'keep-alive'
        cherrypy.response.headers['Access-Control-Allow-Origin'] = '*'

        q = queue.Queue(maxsize=100)
        with self.listeners_lock:
            self.listeners.add(q)

        def event_generator():
            try:
                while True:
                    try:
                        msg = q.get(timeout=15)
                        yield f"data: {msg}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                with self.listeners_lock:
                    self.listeners.discard(q)

        return event_generator()
    stream._cp_config = {'response.stream': True}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def status(self):
        """GET /api/status endpoint returning cached status dict for all monitored rooms."""
        return self.cache["rooms"]

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def presence(self):
        """GET /api/presence endpoint returning online presence cache for connected services/devices."""
        return self.cache["presence"]
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def command(self):
        """POST /api/command endpoint for sending operator commands (unlock, reset, trigger_prop, play_audio, set_lights) to rooms via MQTT."""
        data = cherrypy.request.json
        room_id = data.get("room_id")
        cmd = data.get("command")
        
        if not room_id or not cmd:
            return {"success": False, "error": "Missing room_id or command"}

        if cmd == "trigger_prop":
            prop_id = data.get("prop_id")
            interaction_type = data.get("interaction_type", "button")
            val = data.get("value", "pressed")
            topic = f"room/{room_id}/prop/{prop_id}/event"
            payload = {
                "prop_id": prop_id,
                "interaction_type": interaction_type,
                "value": val
            }
            self.mqtt.publish(topic, payload, qos=1)
            return {"success": True, "action": "trigger_prop", "topic": topic}

        elif cmd == "play_audio":
            track = data.get("track", "ambient.mp3")
            topic = f"room/{room_id}/room/command"
            payload = {"room_id": room_id, "command": "play_audio", "payload": {"track": track}}
            self.mqtt.publish(topic, payload, qos=2)
            return {"success": True, "action": "play_audio", "track": track}

        elif cmd == "set_lights":
            color = data.get("color", "cyan")
            topic = f"room/{room_id}/room/command"
            payload = {"room_id": room_id, "command": "set_lights", "payload": {"color": color}}
            self.mqtt.publish(topic, payload, qos=2)
            return {"success": True, "action": "set_lights", "color": color}

        else:
            topic = f"command/room/{room_id}"
            payload = {"room_id": room_id, "command": cmd}
            self.mqtt.publish(topic, payload, qos=2)
            self.mqtt.publish(f"room/{room_id}/room/command", payload, qos=2)
            return {"success": True, "action": cmd}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def stats(self, *args, **kwargs):
        """GET /api/stats/* endpoint proxying requests to the backend Analytics microservice."""
        path = "/".join(args)
        analytics_url = f"http://analytics:8084/stats/{path}"
        try:
            r = requests.get(analytics_url, params=kwargs, timeout=5)
            if r.status_code == 200:
                return r.json()
            else:
                cherrypy.response.status = r.status_code
                return {"error": f"Analytics service returned {r.status_code}"}
        except Exception as e:
            cherrypy.response.status = 500
            return {"error": str(e)}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def strategy(self, room_id):
        """GET /api/strategy/{room_id} endpoint proxying requests to the backend Catalog microservice."""
        try:
            r = requests.get(f"http://catalog:8080/config/{room_id}", timeout=5)
            if r.status_code == 200:
                return r.json()
            else:
                return {"error": f"Catalog service returned {r.status_code}"}
        except Exception as e:
            cherrypy.response.status = 500
            return {"error": str(e)}

if __name__ == "__main__":
    api = WebDashboardAPI()
    
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'dist'))
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir, exist_ok=True)
    
    conf = {
        '/': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': dist_dir,
            'tools.staticdir.index': 'index.html',
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Access-Control-Allow-Origin', '*')]
        },
        '/api': {
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Headers', 'Content-Type')
            ]
        }
    }
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8087,
    })
    
    def cors_options():
        if cherrypy.request.method == 'OPTIONS':
            cherrypy.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
            cherrypy.response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return True
    cherrypy.tools.cors_options = cherrypy.Tool('before_handler', cors_options)
    conf['/api']['tools.cors_options.on'] = True

    cherrypy.tree.mount(api, '/api', conf)
    cherrypy.tree.mount(None, '/', conf)
    
    cherrypy.engine.start()
    cherrypy.engine.block()

