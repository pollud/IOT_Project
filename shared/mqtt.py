import paho.mqtt.client as mqtt
import threading
import time
import json

class MQTTClient:
    def __init__(self, client_id, broker="mosquitto", port=1883,
                 heartbeat_topic=None, heartbeat_interval=10, heartbeat_payload=None,
                 lwt_topic=None, lwt_payload=None, lwt_qos=1):
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id, clean_session=True)
        
        # Logging callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        
        # Callbacks map
        self.on_message_callback = None
        self.client.on_message = self._on_message
        
        # Subscriptions
        self._subscriptions = []
        
        # LWT Default configuration
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
        self.connected = False
        print(f"[{self.client_id}] Disconnected from broker (code {rc}). Reconnecting...")
        
    def _on_message(self, client, userdata, msg):
        if self.on_message_callback:
            self.on_message_callback(msg.topic, msg.payload.decode())

    def start(self):
        self.running = True
        self.client.connect_async(self.broker, self.port, 60)
        self.client.loop_start()
        
        if self.heartbeat_topic:
            t = threading.Thread(target=self._heartbeat_loop, daemon=True)
            t.start()
            
    def stop(self):
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()
        
    def _heartbeat_loop(self):
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
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        elif not isinstance(payload, (str, bytes)):
            # Fallback for dataclasses if utils.to_json was meant to be used, but we keep it generic
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
        if (topic, qos) not in self._subscriptions:
            self._subscriptions.append((topic, qos))
        if self.connected:
            self.client.subscribe(topic, qos=qos)
