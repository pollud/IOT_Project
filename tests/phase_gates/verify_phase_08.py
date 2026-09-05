"""Phase Gate 08 Verification Test: Validates Safety Monitor service fall detection, emergency override broadcasting, and system alert publishing."""

import os
import subprocess
import sys
import time

import requests


def verify_phase_8():
    """Verify safety_monitor fall detection processing, emergency broadcast to MQTT command/emergency, and room actuator override logging."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including safety_monitor)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    # wait for safety monitor to start
    time.sleep(3)

    from shared.models import BadgeSafetyEvent
    from shared.mqtt import MQTTClient
    
    received_emergency = False
    received_alert = False
    
    def on_msg(topic, payload):
        nonlocal received_emergency, received_alert
        if "command/emergency" in topic:
            received_emergency = True
        elif "system/alerts" in topic:
            received_alert = True
            
    client = MQTTClient("test_phase_8", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("command/emergency")
    client.subscribe("system/alerts")
    
    # Send fake fall event
    fall = BadgeSafetyEvent(badge_id="b1", fall_detected=True)
    client.publish("game/room1/badge/b1/safety", fall)
    
    # Wait for alerts and emergency
    start_time = time.time()
    while not (received_emergency and received_alert) and time.time() - start_time < 3:
        time.sleep(0.1)
        
    if not received_emergency or not received_alert:
        print(f"FAIL: Missing topics. emergency={received_emergency}, alert={received_alert}")
        sys.exit(1)
        
    # verify room connector logged it
    try:
        r = requests.get("http://localhost:8081/actuator/health")
        logs = r.json().get("logs", [])
        has_emerg = any(entry.get("type") == "emergency" for entry in logs)
        if not has_emerg:
            print("FAIL: Emergency command was not logged by room_connector.")
            sys.exit(1)
    except Exception as e:
        print(f"FAIL: Could not connect to room_connector to verify logs: {e}")
        sys.exit(1)

    client.stop()
    print("PASS: Phase 8 verification passed")

if __name__ == '__main__':
    verify_phase_8()

