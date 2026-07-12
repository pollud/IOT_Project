import os
import time
import json
import threading
import cherrypy
from shared.mqtt import MQTTClient

class TelegramBot:
    def __init__(self):
        self.broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.token = os.getenv("TELEGRAM_TOKEN", "")
        
        self.cache = {
            "alerts": [],
            "status": {}
        }
        
        self.mqtt = MQTTClient(
            client_id="telegram_bot",
            broker=self.broker
        )
        self.mqtt.on_message_callback = self.on_message
        
        def run_mqtt():
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
                    time.sleep(2)
            self.mqtt.subscribe("system/alerts")
            self.mqtt.subscribe("room/+/status")
            
        t = threading.Thread(target=run_mqtt, daemon=True)
        t.start()
        
    def on_message(self, topic, payload):
        try:
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8')
            elif isinstance(payload, dict):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)
                
            data = json.loads(payload_str)
            if "status" in topic:
                room_id = topic.split("/")[1]
                self.cache["status"][room_id] = data
            elif "alerts" in topic:
                self.cache["alerts"].append(data)
                
        except Exception as e:
            pass
            
    def handle_command(self, cmd, args):
        if cmd == "/status":
            return json.dumps(self.cache["status"])
        elif cmd == "/open":
            room_id = args[0] if args else "room1"
            self.mqtt.publish("command/room", {"room_id": room_id, "command": "unlockDoor"})
            return f"Opening {room_id}"
        elif cmd == "/reset":
            room_id = args[0] if args else "room1"
            self.mqtt.publish("command/room", {"room_id": room_id, "command": "reset"})
            return f"Resetting {room_id}"
        elif cmd == "/help":
            return "/status, /open <room>, /reset <room>"
        return "Unknown command"
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def webhook(self):
        data = cherrypy.request.json
        text = data.get("message", {}).get("text", "")
        parts = text.split(" ")
        cmd = parts[0]
        args = parts[1:]
        
        start_time = time.time()
        reply = self.handle_command(cmd, args)
        duration = time.time() - start_time
        
        return {"reply": reply, "duration": duration}

if __name__ == "__main__":
    bot = TelegramBot()
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8086,
    })
    cherrypy.quickstart(bot)
