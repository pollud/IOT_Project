import os
import sys
import subprocess
import time
import requests
import json
import random

def verify_phase_13():
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including telegram_bot)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)
    
    # Wait for REST API
    up = False
    for _ in range(15):
        try:
            r = requests.post("http://localhost:8086/webhook", json={"message": {"text": "/status"}})
            if r.status_code == 200:
                up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        time.sleep(1)
        
    if not up:
        print("FAIL: Telegram Bot REST API never came up on port 8086.")
        sys.exit(1)

    # 1. Test /status replies in < 1.0s
    t0 = time.time()
    r = requests.post("http://localhost:8086/webhook", json={"message": {"text": "/status"}})
    duration = time.time() - t0
    
    if r.status_code != 200:
        print(f"FAIL: GET status failed with code {r.status_code}")
        sys.exit(1)
        
    if duration > 1.0:
        print(f"FAIL: /status took too long: {duration}s")
        sys.exit(1)

    print(f"PASS: /status replied in {duration:.3f}s")
    
    # 2. Test /open results in command/room
    from shared.mqtt import MQTTClient
    
    received_commands = []
    
    def on_msg(topic, payload):
        if "command/room" in topic:
            if isinstance(payload, bytes):
                payload = payload.decode('utf-8')
            received_commands.append(json.loads(payload))
            
    client = MQTTClient("test_phase_13", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("command/room")
    time.sleep(1) # wait for sub
    
    print("Testing /open room1...")
    r = requests.post("http://localhost:8086/webhook", json={"message": {"text": "/open room1"}})
    
    time.sleep(3)
    client.stop()
    
    found = False
    for cmd in received_commands:
        if cmd.get("command") == "unlockDoor" and cmd.get("room_id") == "room1":
            found = True
            break
            
    if not found:
        print("FAIL: Expected command/room unlockDoor message not received")
        sys.exit(1)

    print("PASS: Phase 13 verification passed")

if __name__ == '__main__':
    verify_phase_13()
