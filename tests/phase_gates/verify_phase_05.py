"""Phase Gate 05 Verification Test: Validates Room Connector service environmental telemetry publishing and room/emergency actuator command logging."""

import os
import sys
import subprocess
import time
import requests
import json

def verify_phase_5():
    """Verify room_connector environmental telemetry output, command processing, and REST endpoint (/actuator/health)."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    print("Bringing up docker-compose (including room_connector)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    print("Waiting for room_connector to start...")
    # Wait for REST API
    rc_up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8081/calibration")
            if r.status_code == 200:
                rc_up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
        
    if not rc_up:
        print("FAIL: Room connector REST API never came up on port 8081.")
        sys.exit(1)

    # Subscribe to environment messages
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from shared.mqtt import MQTTClient
    from shared.models import RoomCommand
    
    env_received = False
    
    def on_msg(topic, payload):
        nonlocal env_received
        if "environment" in topic:
            env_received = True
            
    client = MQTTClient("test_phase_5", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("room/room1/environment")
    
    # Wait for environment message
    start_time = time.time()
    while not env_received and time.time() - start_time < 5:
        time.sleep(0.1)
        
    if not env_received:
        print("FAIL: Did not receive environment telemetry from room_connector.")
        sys.exit(1)

    # Publish commands
    print("Publishing command/room/room1 ...")
    room_cmd = RoomCommand(command="unlock", target="door")
    client.publish("command/room/room1", room_cmd)
    
    print("Publishing command/emergency ...")
    emerg_cmd = RoomCommand(command="emergency_unlock")
    client.publish("command/emergency", emerg_cmd)
    
    time.sleep(2)
    client.stop()
    
    # Check actuator logs
    r = requests.get("http://localhost:8081/actuator/health")
    logs = r.json().get("logs", [])
    
    has_room = any(l.get("type") == "room_command" for l in logs)
    has_emerg = any(l.get("type") == "emergency" for l in logs)
    
    if not has_room:
        print("FAIL: Room command was not logged by room_connector.")
        sys.exit(1)
        
    if not has_emerg:
        print("FAIL: Emergency command was not logged by room_connector.")
        sys.exit(1)

    print("PASS: Phase 5 verification passed")

if __name__ == '__main__':
    verify_phase_5()

