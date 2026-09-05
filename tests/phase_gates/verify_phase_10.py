"""Phase Gate 10 Verification Test: Validates TimeSeries Adapter service telemetry event ingestion and SQLite database persistence."""

import os
import random
import sqlite3
import subprocess
import sys
import time


def verify_phase_10():
    """Verify timeseries_adapter service database initialization, batch ingestion queue, and SQLite records storage."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    # Ensure data directory exists
    data_dir = os.path.join(project_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    print("Bringing up docker-compose (including timeseries_adapter)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)

    from shared.mqtt import MQTTClient
    
    client = MQTTClient("test_phase_10", broker="localhost")
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    random_temp = 999.0 + random.random()
    payload = {"temperature": random_temp, "humidity": 50.0}
    topic = "room/room1/environment"
    
    print(f"Publishing dummy event with temperature {random_temp}...")
    client.publish(topic, payload)
    
    time.sleep(3)
    client.stop()
    
    db_path = os.path.join(data_dir, 'events.db')
    if not os.path.exists(db_path):
        print(f"FAIL: Database file not found at {db_path}")
        sys.exit(1)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT payload FROM events WHERE topic = ?", (topic,))
    rows = cursor.fetchall()
    
    found = False
    for row in rows:
        payload_str = row[0]
        if str(random_temp) in payload_str:
            found = True
            break
            
    if not found:
        print(f"FAIL: Dummy event with temp {random_temp} not found in database.")
        sys.exit(1)
        
    print("PASS: Phase 10 verification passed")

if __name__ == '__main__':
    verify_phase_10()

