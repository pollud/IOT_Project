import os
import sys
import subprocess
import time
import requests
import json

def verify_phase_14():
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including node_red)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(5)
    
    # Wait for Node-RED API
    up = False
    for _ in range(30):
        try:
            r = requests.get("http://localhost:1880/ui")
            if r.status_code == 200:
                up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        time.sleep(2)
        
    if not up:
        print("FAIL: Node-RED dashboard never came up on port 1880.")
        sys.exit(1)

    print("Dashboard loaded.")
    
    from shared.mqtt import MQTTClient
    
    received_commands = []
    
    def on_msg(topic, payload):
        if "command/room" in topic:
            if isinstance(payload, bytes):
                payload = payload.decode('utf-8')
            received_commands.append(json.loads(payload))
            
    client = MQTTClient("test_phase_14", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("command/room")
    time.sleep(1) # wait for sub
    
    print("Triggering manual control via Node-RED API...")
    r = requests.post("http://localhost:1880/test_open")
    if r.status_code != 200:
        print(f"FAIL: HTTP POST to test_open failed: {r.status_code}")
        sys.exit(1)
        
    time.sleep(3)
    client.stop()
    
    found = False
    for cmd in received_commands:
        if cmd.get("command") == "unlockDoor" and cmd.get("room_id") == "room1":
            found = True
            break
            
    if not found:
        print("FAIL: Expected command/room unlockDoor message not received from Node-RED")
        sys.exit(1)

    print("PASS: Phase 14 verification passed")

if __name__ == '__main__':
    verify_phase_14()
