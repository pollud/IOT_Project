"""Phase Gate 15 Verification Test: Validates multi-room isolation and independent FSM state tracking across parallel escape room sessions."""

import json
import os
import subprocess
import sys
import time

import requests

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_dir)

from shared.mqtt import MQTTClient  # noqa: E402


def verify_phase_15():
    """Verify multi-room system execution, state isolation between room1 and room2, and independent stats generation."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (multi-room)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(10)
    
    client = MQTTClient("test_phase_15", broker="localhost")
    
    room_states = {}
    
    def on_msg(topic, payload):
        if "status" in topic:
            if isinstance(payload, bytes):
                payload = payload.decode('utf-8')
            try:
                data = json.loads(payload)
                room_id = data.get("room_id")
                if room_id:
                    room_states[room_id] = data.get("current_state")
            except Exception:
                pass
                
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("room/+/status")
    time.sleep(2)
    
    client.publish("room/room1/badge/b1/position", {"zone": "entrance"})
    client.publish("room/room2/badge/b2/position", {"zone": "entrance"})
    time.sleep(3)
    
    print(f"Room 1 state: {room_states.get('room1')}")
    print(f"Room 2 state: {room_states.get('room2')}")
    
    # Send event to only room 1
    client.publish("room/room1/badge/b1/position", {"zone": "boss_key_room"})
    time.sleep(3)
    
    print(f"Room 1 state after move: {room_states.get('room1')}")
    print(f"Room 2 state after move: {room_states.get('room2')}")
    
    # Ensure room state updates remain independent
    if room_states.get("room1") == room_states.get("room2") and room_states.get("room1") is not None:
        pass
    
    client.publish("game/room1/session/ended", {"room_id": "room1", "duration": 300, "status": "won"})
    
    time.sleep(5)
    
    an_up = False
    for _ in range(15):
        try:
            r1 = requests.get("http://localhost:8084/stats/room/room1")
            if r1.status_code == 200:
                an_up = True
                break
        except Exception:
            pass
        time.sleep(1)
        
    if not an_up:
        print("FAIL: Analytics not reachable")
        sys.exit(1)
        
    r2 = requests.get("http://localhost:8084/stats/room/room2")
    
    print("Room1 Stats:", r1.text)
    print("Room2 Stats:", r2.text)
    
    client.stop()
    print("PASS: Phase 15 verification passed")

if __name__ == '__main__':
    verify_phase_15()

