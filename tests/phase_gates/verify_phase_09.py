"""Phase Gate 09 Verification Test: Validates Room FSM Controller strategy loading, hot-swap reconfiguration, event transitions, timed transitions, and completion status."""

import os
import sys
import subprocess
import time
import json

def verify_phase_9():
    """Verify room_control FSM engine execution, strategy hot-swapping, prop interaction triggers, timer scheduling, and game completion events."""
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    sys.path.insert(0, project_dir)
    
    # Reset strategy to v1
    v1_strategy = {
        "room_id": "room1", "version": "zelda_dungeon_v1", "initial_state": "entrance_locked",
        "states": {
            "entrance_locked": {
                "on_enter": [{"action": "publishStatus", "status": "started"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "switch_1", "interaction_type": "button", "value": "pressed", "target_state": "main_chamber"}]
            },
            "main_chamber": {
                "on_enter": [{"action": "playAudio", "track": "secret_sound.mp3"}],
                "transitions": [
                    {"trigger": "time", "duration_seconds": 3, "target_state": "hint_needed"},
                    {"trigger": "event", "event_type": "PropEvent", "prop_id": "boss_key_reader", "interaction_type": "rfid", "value": "triforce_key", "target_state": "boss_room"}
                ]
            },
            "hint_needed": {
                "on_enter": [{"action": "playAudio", "track": "navi_listen.mp3"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "boss_key_reader", "interaction_type": "rfid", "value": "triforce_key", "target_state": "boss_room"}
            ]},
            "boss_room": {
                "on_enter": [{"action": "playAudio", "track": "boss_music.mp3"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "master_sword", "interaction_type": "capacitive", "value": "touched", "target_state": "game_cleared"}]
            },
            "game_cleared": {
                "on_enter": [{"action": "publishStatus", "status": "completed"}],
                "transitions": []
            }
        }
    }
    
    strategy_path = os.path.join(project_dir, 'config', 'strategy_room1.json')
    with open(strategy_path, 'w') as f:
        json.dump(v1_strategy, f, indent=2)
        
    print("Bringing up docker-compose (including room_control)...")
    subprocess.check_call(["docker-compose", "up", "-d", "--build"], cwd=project_dir)
            
    time.sleep(3)

    from shared.mqtt import MQTTClient
    
    commands = []
    status_updates = []
    
    def on_msg(topic, payload):
        if "command" in topic:
            commands.append(json.loads(payload))
        elif "status" in topic:
            status_updates.append(json.loads(payload))
            
    client = MQTTClient("test_phase_9", broker="localhost")
    client.on_message_callback = on_msg
    client.start()
    
    while not client.connected:
        time.sleep(0.1)
        
    client.subscribe("command/room/room1")
    client.subscribe("game/room1/status")
    
    # 1. Hot Swap test
    v2_strategy = v1_strategy.copy()
    v2_strategy["version"] = "zelda_dungeon_v2"
    with open(strategy_path, 'w') as f:
        json.dump(v2_strategy, f, indent=2)
        
    # simulate catalog config-update
    client.publish("catalog/room1/config-update", {"version": "zelda_dungeon_v2"})
    time.sleep(2)
    
    # Check if 'started' status was re-published due to reload
    if not any(s.get("status") == "started" for s in status_updates):
        print(f"FAIL: Did not re-enter initial state on hot swap. Statuses: {status_updates}")
        sys.exit(1)
        
    status_updates.clear()
    commands.clear()
    
    # 2. Trigger events sequence
    # step 1: switch_1 -> main_chamber -> playAudio secret_sound.mp3
    client.publish("game/room1/prop/switch_1/interaction", {"prop_id": "switch_1", "interaction_type": "button", "value": "pressed"})
    time.sleep(1)
    if not any(c.get("payload", {}).get("track") == "secret_sound.mp3" for c in commands):
        print(f"FAIL: main_chamber actions not executed. Commands: {commands}")
        sys.exit(1)
        
    commands.clear()
    
    # step 2: Wait 3 seconds for time transition to hint_needed -> playAudio navi_listen.mp3
    print("Waiting 4 seconds for time transition...")
    time.sleep(4)
    if not any(c.get("payload", {}).get("track") == "navi_listen.mp3" for c in commands):
        print(f"FAIL: hint_needed actions not executed. Commands: {commands}")
        sys.exit(1)
        
    commands.clear()
    
    # step 3: boss_key_reader -> boss_room
    client.publish("game/room1/prop/boss_key_reader/interaction", {"prop_id": "boss_key_reader", "interaction_type": "rfid", "value": "triforce_key"})
    time.sleep(1)
    if not any(c.get("payload", {}).get("track") == "boss_music.mp3" for c in commands):
        print(f"FAIL: boss_room actions not executed. Commands: {commands}")
        sys.exit(1)
        
    commands.clear()
    
    # step 4: master_sword -> game_cleared -> status completed
    client.publish("game/room1/prop/master_sword/interaction", {"prop_id": "master_sword", "interaction_type": "capacitive", "value": "touched"})
    time.sleep(1)
    if not any(s.get("status") == "completed" for s in status_updates):
        print(f"FAIL: game_cleared status not published. Statuses: {status_updates}")
        sys.exit(1)

    client.stop()
    print("PASS: Phase 9 verification passed")

if __name__ == '__main__':
    verify_phase_9()

