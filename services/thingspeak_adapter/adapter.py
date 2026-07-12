import os
import time
import json
import cherrypy
import threading
from shared.mqtt import MQTTClient

class ThingSpeakAdapter:
    def __init__(self):
        self.broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.api_key = os.getenv("THINGSPEAK_API_KEY", "")
        self.history_data = []
        
        self.mqtt = MQTTClient(
            client_id="thingspeak_adapter",
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
                    print(e)
                    time.sleep(2)
            self.mqtt.subscribe("room/+/environment")
            self.mqtt.subscribe("analytics")
        
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
                
            entry = {
                "timestamp": time.time(),
                "topic": topic,
                "payload": payload_str
            }
            self.history_data.append(entry)
            
            if len(self.history_data) > 100:
                self.history_data.pop(0)
                
        except Exception as e:
            print(f"Error processing message: {e}")

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def history(self):
        return self.history_data

if __name__ == "__main__":
    adapter = ThingSpeakAdapter()
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8085,
    })
    cherrypy.quickstart(adapter)
