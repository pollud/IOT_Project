"""Phase Gate 00 Verification Test: Validates architecture documentation and expected data model definitions in docs/mqtt_topics.md and docs/phase_gates.md."""

import os
import re
import sys

def verify_phase_0():
    """Verify presence of documentation files and completeness of topic taxonomy and phase gate definitions."""
    docs_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'docs')
    mqtt_topics_path = os.path.join(docs_dir, 'mqtt_topics.md')
    phase_gates_path = os.path.join(docs_dir, 'phase_gates.md')

    # Expected dataclasses based on Phase 1 description
    expected_models = {
        'BadgePositionEvent', 'BadgeSafetyEvent', 'EnvironmentEvent', 
        'BatteryEvent', 'PropEvent', 'RoomCommand', 'AlertEvent', 
        'GameStatus', 'HeartbeatEvent', 'SessionEndedEvent', 'ConfigUpdateEvent'
    }

    if not os.path.exists(mqtt_topics_path):
        print(f"FAIL: {mqtt_topics_path} does not exist")
        sys.exit(1)

    if not os.path.exists(phase_gates_path):
        print(f"FAIL: {phase_gates_path} does not exist")
        sys.exit(1)

    with open(mqtt_topics_path, 'r') as f:
        mqtt_content = f.read()

    missing_models = []
    for model in expected_models:
        if model not in mqtt_content:
            missing_models.append(model)
            
    if missing_models:
        print(f"FAIL: The following expected models were not found in mqtt_topics.md: {missing_models}")
        sys.exit(1)

    with open(phase_gates_path, 'r') as f:
        phase_gates_content = f.read()

    missing_phases = []
    for i in range(1, 17):
        if f"Phase {i}" not in phase_gates_content:
            missing_phases.append(i)

    if missing_phases:
        print(f"FAIL: The following phases are missing from phase_gates.md: {missing_phases}")
        sys.exit(1)

    print("PASS: Phase 0 verification passed")

if __name__ == '__main__':
    verify_phase_0()

