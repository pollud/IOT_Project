import os
import time
import json
import sqlite3
from shared.mqtt import MQTTClient

class TimeSeriesAdapter:
    def __init__(self):
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.db_path = os.getenv("DB_PATH", "/app/data/events.db")
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_db()
        
        self.mqtt = MQTTClient(
            client_id="tsdb_adapter",
            broker=broker
        )
        self.mqtt.on_message_callback = self.on_message
        
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
                
        self.mqtt.subscribe("#")
        
    def init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                topic TEXT,
                payload JSON
            )
        ''')
        self.conn.commit()
        
    def on_message(self, topic, payload):
        query = "INSERT INTO events (topic, payload) VALUES (?, ?)"
        try:
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8')
            elif isinstance(payload, dict):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)
                
            self.cursor.execute(query, (topic, payload_str))
            self.conn.commit()
        except Exception as e:
            print(f"Error saving to db: {e}")

if __name__ == "__main__":
    adapter = TimeSeriesAdapter()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        adapter.mqtt.stop()
        adapter.conn.close()
