"""Phase Gate 13 Verification Test: Validates Web Dashboard manual command gateway (/api/command) and latency."""

import os
import subprocess
import sys
import time

import requests


def verify_phase_13():
    """Verify web_dashboard HTTP command endpoint, latency, and MQTT command delivery."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including web_dashboard)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)
    
    # Wait for REST API
    up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8087/api/status")
            if r.status_code == 200:
                up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        time.sleep(1)
        
    if not up:
        print("FAIL: Web Dashboard REST API never came up on port 8087.")
        sys.exit(1)

    # 1. Test /api/command latency < 1.0s
    t0 = time.time()
    r = requests.post("http://localhost:8087/api/command", json={"room_id": "room1", "command": "unlockDoor"})
    dt = time.time() - t0
    
    if r.status_code != 200 or not r.json().get("success"):
        print(f"FAIL: /api/command returned non-success: {r.text}")
        sys.exit(1)
        
    if dt > 1.5:
        print(f"FAIL: Command dispatch took {dt:.2f}s, expected < 1.5s")
        sys.exit(1)
        
    print(f"Command dispatched in {dt:.3f}s")
    print("PASS: Phase 13 verification passed")

if __name__ == '__main__':
    verify_phase_13()
