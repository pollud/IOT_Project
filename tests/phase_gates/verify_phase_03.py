"""Phase Gate 03 Verification Test: Validates Catalog REST endpoints (/register, /devices) and hot-reload file watching to MQTT config-update topic."""

import os
import sys
import subprocess
import time
import requests
import json

def install_requirements():
    """Install project dependencies from requirements.txt silently."""
    req_file = os.path.join(os.path.dirname(__file__), '..', '..', 'requirements.txt')
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"])

def verify_phase_3():
    """Verify Catalog REST service health, register endpoint, and strategy file update MQTT publication."""
    try:
        install_requirements()
    except Exception as e:
        print(f"Failed to install requirements: {e}")
        sys.exit(1)

    import paho.mqtt.client as mqtt

    # Bring up docker-compose
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    print("Bringing up docker-compose (including catalog)...")
    try:
        subprocess.check_call(["docker", "compose", "up", "-d", "--build"], cwd=project_dir)
    except Exception as e:
        try:
            subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
        except Exception as e2:
            print(f"FAIL: Failed to start docker-compose: {e2}")
            sys.exit(1)
            
    print("Waiting for Catalog to start...")
    # Wait for REST API
    catalog_up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8080/services")
            if r.status_code == 200:
                catalog_up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
        
    if not catalog_up:
        print("FAIL: Catalog REST API never came up on port 8080.")
        sys.exit(1)

    # 1. Register fake device and confirm it
    print("Testing REST API /register and /devices...")
    fake_device = {"type": "device", "id": "badge_1"}
    r = requests.post("http://localhost:8080/register", json=fake_device)
    assert r.status_code == 200, f"Register failed: {r.text}"
    
    r = requests.get("http://localhost:8080/devices")
    devices = r.json().get("devices", [])
    assert any(d.get("id") == "badge_1" for d in devices), "Fake device not in /devices output"
    
    # 2. Test manual config edit -> MQTT config-update
    print("Testing config watch to MQTT...")
    
    message_received = False

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe("catalog/room_test/config-update")
        else:
            print(f"Failed to connect to Mosquitto, rc {rc}")

    def on_message(client, userdata, msg):
        nonlocal message_received
        payload = json.loads(msg.payload.decode())
        if payload.get("version") == "v2_test":
            message_received = True
            client.disconnect()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect("localhost", 1883, 60)
        client.loop_start()
    except Exception as e:
        print(f"FAIL: MQTT connection error: {e}")
        sys.exit(1)

    # Write a new config to trigger watch
    test_config_path = os.path.join(project_dir, "config", "strategy_room_test.json")
    with open(test_config_path, "w") as f:
        json.dump({"version": "v1_test"}, f)
        
    time.sleep(1) # wait a moment for initial pick up
    
    # Edit the config to v2_test
    with open(test_config_path, "w") as f:
        json.dump({"version": "v2_test"}, f)
        
    # Wait up to 2 seconds for message
    start_time = time.time()
    while not message_received and time.time() - start_time < 3:
        time.sleep(0.1)
        
    client.loop_stop()
    
    if os.path.exists(test_config_path):
        os.remove(test_config_path)

    if not message_received:
        print("FAIL: Config update MQTT message not received.")
        sys.exit(1)

    print("PASS: Phase 3 verification passed")

if __name__ == '__main__':
    verify_phase_3()

