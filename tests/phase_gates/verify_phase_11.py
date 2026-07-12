import os
import sys
import subprocess
import time
import requests
import json
import sqlite3
import random

def verify_phase_11():
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    print("Bringing up docker-compose (including analytics)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)
    
    # Insert 3 specific prop usage events into SQLite
    test_prop_id = f"test_prop_{random.randint(1000, 9999)}"
    topic = "game/room1/prop/test/interaction"
    payload = json.dumps({"prop_id": test_prop_id, "interaction_type": "button", "value": "pressed"})
    
    # Run python snippet inside analytics container to avoid macOS/Docker sqlite lock corruption
    py_script = f"""
import sqlite3
import time
# retry connection if locked
connected = False
for _ in range(5):
    try:
        conn = sqlite3.connect('/app/data/events.db', timeout=10)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            topic TEXT,
            payload JSON
        )''')
        for _ in range(3):
            cursor.execute("INSERT INTO events (topic, payload) VALUES (?, ?)", ('{topic}', '{payload}'))
        conn.commit()
        conn.close()
        connected = True
        break
    except sqlite3.OperationalError:
        time.sleep(1)
if not connected:
    raise Exception("Could not initialize and insert into DB")
"""
    subprocess.check_call(["docker-compose", "exec", "-T", "analytics", "python", "-c", py_script], cwd=project_dir)

    # Wait for analytics REST API
    an_up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8084/stats/room/room1")
            if r.status_code == 200:
                an_up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        time.sleep(1)
        
    if not an_up:
        print("FAIL: Analytics REST API never came up on port 8084.")
        sys.exit(1)
    
    # Hit GET /stats/prop/<id>
    r = requests.get(f"http://localhost:8084/stats/prop/{test_prop_id}")
    if r.status_code != 200:
        print(f"FAIL: GET stats failed with code {r.status_code}")
        sys.exit(1)
        
    data = r.json()
    usage = data.get("usage_count")
    
    if usage != 3:
        print(f"FAIL: Expected usage_count=3, got {usage}")
        sys.exit(1)

    print("PASS: Phase 11 verification passed")

if __name__ == '__main__':
    verify_phase_11()
