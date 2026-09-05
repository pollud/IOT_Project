"""Phase Gate 12 Verification Test: Validates Analytics Engine REST API endpoints and data aggregation."""

import os
import subprocess
import sys
import time

import requests


def verify_phase_12():
    """Verify Analytics Engine container startup and /stats REST endpoints response structure."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    print("Bringing up docker-compose (including analytics)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)
    
    # Wait for REST API
    up = False
    for _ in range(15):
        try:
            r = requests.get("http://localhost:8084/stats/game_center")
            if r.status_code == 200:
                up = True
                break
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        time.sleep(1)
        
    if not up:
        print("FAIL: Analytics Engine REST API never came up on port 8084.")
        sys.exit(1)

    # 1. Test game center stats endpoint
    r = requests.get("http://localhost:8084/stats/game_center")
    if r.status_code != 200 or "kpis" not in r.json():
        print(f"FAIL: GET /stats/game_center invalid response: {r.text}")
        sys.exit(1)
    print("GET /stats/game_center OK")

    # 2. Test safety score endpoint
    r_safety = requests.get("http://localhost:8084/stats/safety")
    if r_safety.status_code != 200 or "safety_score_pct" not in r_safety.json():
        print(f"FAIL: GET /stats/safety invalid response: {r_safety.text}")
        sys.exit(1)
    print("GET /stats/safety OK")

    print("PASS: Phase 12 verification passed")

if __name__ == '__main__':
    verify_phase_12()
