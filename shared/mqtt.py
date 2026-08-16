"""MQTT Client Wrapper providing automated reconnection, presence (LWT), heartbeat signaling, and topic subscription management."""

import paho.mqtt.client as mqtt
import threading
import time
import json

class MQTTClient:
    """Wrapper around paho-mqtt Client to manage connections, heartbeats, and Last Will and Testament (LWT)."""

    def __init__(self, client_id, broker="mosquitto", port=1883,
                 heartbeat_topic=None, heartbeat_interval=10, heartbeat_payload=None,
                 lwt_topic=None, lwt_payload=None, lwt_qos=1):
        """Initialize the MQTTClient instance.

        Args:
            client_id (str): Unique client identifier.
            broker (str): MQTT broker hostname or IP address.
            port (int): MQTT broker port (default 1883).
            heartbeat_topic (str, optional): Topic to publish periodic heartbeats.
            heartbeat_interval (int): Interval in seconds between heartbeat publications.
            heartbeat_payload (Any, optional): Data or callable returning data for heartbeats.
            lwt_topic (str, optional): Last Will and Testament topic. Defaults to status/<client_id>.
            lwt_payload (Any, optional): Last Will and Testament offline payload.
            lwt_qos (int): QoS level for LWT message.
        """
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id, clean_session=True)
        
        # Logging callbacks setup
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        
        # External message callback mapping
        self.on_message_callback = None
        self.client.on_message = self._on_message
        
        # Active subscription topics registry
        self._subscriptions = []
        
        # LWT Default configuration setup
        if lwt_topic is None and client_id:
            lwt_topic = f"status/{client_id}"
            lwt_payload = {"service": client_id, "status": "offline", "timestamp": time.time()}
        
        self.presence_topic = lwt_topic
        
        if lwt_topic and lwt_payload:
            payload_str = json.dumps(lwt_payload) if isinstance(lwt_payload, dict) else str(lwt_payload)
            self.client.will_set(lwt_topic, payload=payload_str, qos=lwt_qos, retain=True)

        self.heartbeat_topic = heartbeat_topic
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_payload = heartbeat_payload
        self.running = False
        self.connected = False
        
    def _on_connect(self, client, userdata, flags, rc):
        """Internal callback executed when client connects to broker."""
        if rc == 0:
            self.connected = True
            print(f"[{self.client_id}] Connected to broker.")
            # Publish online presence (retained)
            if self.presence_topic:
                online_payload = {"service": self.client_id, "status": "online", "timestamp": time.time()}
                self.publish(self.presence_topic, online_payload, qos=1, retain=True)
            # Resubscribe on reconnect
            for topic, qos in self._subscriptions:
                self.client.subscribe(topic, qos=qos)
        else:
            print(f"[{self.client_id}] Connection failed with code {rc}")
            
    def _on_disconnect(self, client, userdata, rc):
        """Internal callback executed when client disconnects from broker."""
        self.connected = False
        print(f"[{self.client_id}] Disconnected from broker (code {rc}). Reconnecting...")
        
    def _on_message(self, client, userdata, msg):
        """Internal callback delegating incoming MQTT messages to registered callback."""
        if self.on_message_callback:
            self.on_message_callback(msg.topic, msg.payload.decode())

    def start(self):
        """Connect to broker and start the network loop and heartbeat background thread."""
        self.running = True
        self.client.connect_async(self.broker, self.port, 60)
        self.client.loop_start()
        
        if self.heartbeat_topic:
            t = threading.Thread(target=self._heartbeat_loop, daemon=True)
            t.start()
            
    def stop(self):
        """Stop background network loop and disconnect from broker."""
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()
        
    def _heartbeat_loop(self):
        """Background thread loop for periodic heartbeat publication."""
        while self.running:
            if self.connected:
                try:
                    payload = self.heartbeat_payload() if callable(self.heartbeat_payload) else self.heartbeat_payload
                    if payload:
                        self.publish(self.heartbeat_topic, payload)
                except Exception as e:
                    print(f"[{self.client_id}] Heartbeat error: {e}")
            time.sleep(self.heartbeat_interval)
            
    def publish(self, topic, payload, qos=0, retain=False):
        """Publish a message to an MQTT topic.

        Args:
            topic (str): Target MQTT topic string.
            payload (Any): Payload object, dict, string, or dataclass to publish.
            qos (int): Quality of Service level (0, 1, or 2).
            retain (bool): Whether broker should retain the message.
        """
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        elif not isinstance(payload, (str, bytes)):
            # Fallback for dataclasses
            if hasattr(payload, '__dict__'):
                import dataclasses
                if dataclasses.is_dataclass(payload):
                    payload = json.dumps(dataclasses.asdict(payload))
                else:
                    payload = str(payload)
            else:
                payload = str(payload)
        self.client.publish(topic, payload, qos=qos, retain=retain)
        
    def subscribe(self, topic, qos=0):
        """Subscribe to an MQTT topic pattern.

        Args:
            topic (str): MQTT topic pattern to subscribe to.
            qos (int): Quality of Service level (0, 1, or 2).
        """
        if (topic, qos) not in self._subscriptions:
            self._subscriptions.append((topic, qos))
        if self.connected:
            self.client.subscribe(topic, qos=qos)

