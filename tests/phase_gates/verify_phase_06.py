"""Phase Gate 06 Verification Test: Validates Badge Connector telemetry publishing (position, battery, heartbeat) and forced fall safety event trigger."""

import os
import sys
import subprocess
import time
import requests
import json

def verify_phase_6():
    """Verify badge_connector startup, REST trigger endpoint, and MQTT badge telemetry topic reception."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including badge_connector)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    print("Waiting for badge_connector to start...")
    bc_up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8082/force_fall")
            if r.status_code == 200:
                bc_up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
        
    if not bc_up:
        print("FAIL: Badge connector REST API never came up on port 8082.")
        sys.exit(1)

    from shared.mqtt import MQTTClient
    
    received_topics = set()
    
    def on_msg(topic, payload):
        if "position" in topic:
            received_topics.add("position")
        elif "battery" in topic:
            received_topics.add("battery")
        elif "heartbeat" in topic:
            received_topics.add("heartbeat")
        elif "safety" in topic:
            received_topics.add("safety")
            
    client = MQTTClient("test_phase_6", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("game/room1/badge/b1/position")
    client.subscribe("game/room1/badge/b1/battery")
    client.subscribe("game/room1/badge/b1/heartbeat")
    client.subscribe("game/room1/badge/b1/safety")
    
    # Wait for natural topics
    start_time = time.time()
    while time.time() - start_time < 10:
        if {"position", "battery", "heartbeat"}.issubset(received_topics):
            break
        time.sleep(0.5)
        
    # Force a fall
    requests.get("http://localhost:8082/force_fall")
    
    # Wait for safety message
    start_time = time.time()
    while "safety" not in received_topics and time.time() - start_time < 5:
        time.sleep(0.5)
        
    client.stop()
    
    expected = {"position", "battery", "heartbeat", "safety"}
    if not expected.issubset(received_topics):
        missing = expected - received_topics
        print(f"FAIL: Missing topics: {missing}")
        sys.exit(1)

    print("PASS: Phase 6 verification passed")

if __name__ == '__main__':
    verify_phase_6()

