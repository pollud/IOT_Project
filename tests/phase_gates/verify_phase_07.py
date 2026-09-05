"""Phase Gate 07 Verification Test: Validates Prop Connector interaction triggers (button, rfid, capacitive) and background health/heartbeat publishing."""

import json
import os
import subprocess
import sys
import time

import requests


def verify_phase_7():
    """Verify prop_connector HTTP trigger endpoints and MQTT interaction message output."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including prop_connector)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    print("Waiting for prop_connector to start...")
    pc_up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8083/trigger_button")
            if r.status_code == 200:
                pc_up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
        
    if not pc_up:
        print("FAIL: Prop connector REST API never came up on port 8083.")
        sys.exit(1)

    from shared.mqtt import MQTTClient
    
    interactions = []
    health_received = False
    heartbeat_received = False
    
    def on_msg(topic, payload):
        nonlocal health_received, heartbeat_received
        if "interaction" in topic:
            interactions.append(json.loads(payload))
        elif "health" in topic:
            health_received = True
        elif "heartbeat" in topic:
            heartbeat_received = True
            
    client = MQTTClient("test_phase_7", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("game/room1/prop/prop1/interaction")
    client.subscribe("game/room1/prop/prop1/health")
    client.subscribe("game/room1/prop/prop1/heartbeat")
    
    # Check Button trigger
    interactions.clear()
    requests.get("http://localhost:8083/trigger_button")
    time.sleep(1)
    if len(interactions) != 1 or interactions[0].get("interaction_type") != "button":
        print(f"FAIL: Button trigger failed. interactions={interactions}")
        sys.exit(1)
        
    # Check RFID trigger
    interactions.clear()
    requests.post("http://localhost:8083/trigger_rfid", json={"uid": "xyz"})
    time.sleep(1)
    if len(interactions) != 1 or interactions[0].get("interaction_type") != "rfid":
        print(f"FAIL: RFID trigger failed. interactions={interactions}")
        sys.exit(1)
        
    # Check Capacitive trigger
    interactions.clear()
    requests.get("http://localhost:8083/trigger_cap")
    time.sleep(1)
    if len(interactions) != 1 or interactions[0].get("interaction_type") != "capacitive":
        print(f"FAIL: Cap trigger failed. interactions={interactions}")
        sys.exit(1)
        
    # Check background topics
    start_time = time.time()
    while not (health_received and heartbeat_received) and time.time() - start_time < 5:
        time.sleep(0.5)

    if not health_received or not heartbeat_received:
        print(f"FAIL: Missing background topics. health={health_received}, heartbeat={heartbeat_received}")
        sys.exit(1)
        
    client.stop()
    print("PASS: Phase 7 verification passed")

if __name__ == '__main__':
    verify_phase_7()

