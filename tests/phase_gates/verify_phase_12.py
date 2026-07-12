import os
import sys
import subprocess
import time
import requests
import json
import random

def verify_phase_12():
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including thingspeak_adapter)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)
    
    # Wait for REST API
    up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8085/history")
            if r.status_code == 200:
                up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        time.sleep(1)
        
    if not up:
        print("FAIL: ThingSpeak Adapter REST API never came up on port 8085.")
        sys.exit(1)

    from shared.mqtt import MQTTClient
    
    client = MQTTClient("test_phase_12", broker="localhost")
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    random_temp = 888.0 + random.random()
    payload = {"temperature": random_temp}
    topic = "room/room1/environment"
    
    print(f"Publishing dummy environment event with temp {random_temp}...")
    client.publish(topic, payload)
    
    time.sleep(3)
    client.stop()
    
    r = requests.get("http://localhost:8085/history")
    if r.status_code != 200:
        print(f"FAIL: GET history failed with code {r.status_code}")
        sys.exit(1)
        
    history = r.json()
    found = False
    for entry in history:
        if str(random_temp) in entry.get("payload", ""):
            found = True
            break
            
    if not found:
        print(f"FAIL: Expected history to contain temp {random_temp}")
        sys.exit(1)

    print("PASS: Phase 12 verification passed")

if __name__ == '__main__':
    verify_phase_12()
