"""Prop Connector microservice managing escape room prop telemetry, status heartbeats, and REST API triggers."""

import cherrypy
import os
import time
import threading
import json
from shared.mqtt import MQTTClient
from shared.models import PropEvent, HeartbeatEvent
from shared.topics import build_topic

class PropConnector:
    """Connector managing escape room puzzle props, publishing health metrics, and emitting prop interaction events."""

    def __init__(self, room_id: str, prop_id: str):
        """Initialize PropConnector, connect to MQTT broker, and launch background status thread.

        Args:
            room_id (str): Target room identifier.
            prop_id (str): Specific prop identifier.
        """
        self.room_id = room_id
        self.prop_id = prop_id
        self.total_props = 40
        self.online_props = 40
        
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.mqtt = MQTTClient(
            client_id="prop_connector",
            broker=broker,
            heartbeat_topic="status/prop_connector",
            heartbeat_interval=5,
            heartbeat_payload={
                "service": "prop_connector",
                "status": "online",
                "props_online": self.online_props,
                "props_total": self.total_props,
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
                print(e)
                time.sleep(2)
                
        t = threading.Thread(target=self.publish_health, daemon=True)
        t.start()
        
    def publish_health(self):
        """Background thread publishing periodic presence and health status for connected props."""
        while True:
            self.mqtt.publish("status/prop_connector", {
                "service": "prop_connector",
                "status": "online",
                "props_online": self.online_props,
                "props_total": self.total_props,
                "timestamp": time.time()
            }, qos=1, retain=True)
            time.sleep(5)
            
    def trigger(self, interaction_type: str, value: str):
        """Publish a prop interaction event to MQTT for the configured room and prop ID.

        Args:
            interaction_type (str): Type of interaction (e.g. "button", "RFID", "keypad").
            value (str): Value or payload of interaction (e.g. "pressed", "solved").
        """
        event = PropEvent(prop_id=self.prop_id, interaction_type=interaction_type, value=value)
        self.mqtt.publish(build_topic(self.room_id, "prop", "interaction", self.prop_id), event, qos=1)

class PropRoute:
    """REST Controller for exposing HTTP endpoints to trigger prop interactions manually."""

    def __init__(self, connector: PropConnector):
        """Initialize PropRoute.

        Args:
            connector (PropConnector): Reference to PropConnector instance.
        """
        self.connector = connector
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def trigger_button(self):
        """POST/GET /trigger_button endpoint to simulate a button press interaction on the prop."""
        self.connector.trigger("button", "pressed")
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

