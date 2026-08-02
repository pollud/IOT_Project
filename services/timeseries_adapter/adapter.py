import os
import time
import json
import sqlite3
import queue
import threading
from shared.mqtt import MQTTClient

class TimeSeriesAdapter:
    def __init__(self):
        broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.db_path = os.getenv("DB_PATH", "/app/data/events.db")
        self.batch_size = int(os.getenv("BATCH_SIZE", "50"))
        self.flush_interval = float(os.getenv("FLUSH_INTERVAL", "1.0"))
        self.retention_days = int(os.getenv("RETENTION_DAYS", "7"))
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_db()
        
        self.write_queue = queue.Queue(maxsize=10000)
        self.running = True
        
        # Start DB Batch Writer Worker
        self.writer_thread = threading.Thread(target=self._db_writer_loop, daemon=True)
        self.writer_thread.start()
        
        # Start Retention Pruning Worker
        self.prune_thread = threading.Thread(target=self._prune_loop, daemon=True)
        self.prune_thread.start()
        
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
                
        # Topic Namespace Subscriptions (Scaling optimization)
        self.mqtt.subscribe("room/+/environment")
        self.mqtt.subscribe("room/+/badge/#")
        self.mqtt.subscribe("room/+/prop/#")
        self.mqtt.subscribe("game/+/status")
        self.mqtt.subscribe("game/+/session/#")
        self.mqtt.subscribe("system/alerts")
        
    def init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                topic TEXT,
                payload JSON
            )
        ''')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic_timestamp ON events(topic, timestamp)')
        self.conn.commit()
        
    def on_message(self, topic, payload):
        try:
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8')
            elif isinstance(payload, dict):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)
                
            self.write_queue.put_nowait((topic, payload_str))
        except queue.Full:
            print("TimeSeriesAdapter write queue full! Dropping item to prevent memory bloat.")
        except Exception as e:
            print(f"Error queueing message: {e}")

    def _db_writer_loop(self):
        last_flush = time.time()
        batch = []
        while self.running:
            try:
                try:
                    item = self.write_queue.get(timeout=0.2)
                    batch.append(item)
                except queue.Empty:
                    pass

                now = time.time()
                if len(batch) >= self.batch_size or (batch and (now - last_flush) >= self.flush_interval):
                    self.cursor.executemany("INSERT INTO events (topic, payload) VALUES (?, ?)", batch)
                    self.conn.commit()
                    batch.clear()
                    last_flush = now
            except Exception as e:
                print(f"Error in batch DB write: {e}")

    def _prune_loop(self):
        while self.running:
            time.sleep(3600)  # Prune every hour
            try:
                # Delete raw telemetry older than retention_days
                cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - (self.retention_days * 86400)))
                query = "DELETE FROM events WHERE timestamp < ? AND (topic LIKE '%/environment' OR topic LIKE '%/badge/position')"
                self.cursor.execute(query, (cutoff,))
                self.conn.commit()
                print(f"Pruned old telemetry prior to {cutoff}")
            except Exception as e:
                print(f"Pruning error: {e}")

    def stop(self):
        self.running = False
        self.mqtt.stop()
        self.conn.close()

if __name__ == "__main__":
    adapter = TimeSeriesAdapter()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        adapter.stop()
