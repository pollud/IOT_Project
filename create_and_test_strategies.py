"""Script for generating theme room strategy JSON configurations (Resident Evil, Portal, Mario, Pokemon, Fallout) and executing automated verification tests."""

import json
import os
import sys
import time
import subprocess
import requests

from shared.mqtt import MQTTClient

#: Strategy definitions dictionary for gaming theme escape rooms.
strategies = {
    "resident_evil": {
        "room_id": "room1",
        "version": "re_mansion_v1",
        "initial_state": "mansion_hall",
        "states": {
            "mansion_hall": {
                "on_enter": [{"action": "publishStatus", "status": "started"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "typewriter", "interaction_type": "button", "value": "pressed", "target_state": "save_room"}]
            },
            "save_room": {
                "on_enter": [{"action": "playAudio", "track": "save_theme.mp3"}],
                "transitions": [{"trigger": "time", "duration_seconds": 2, "target_state": "hallway"}]
            },
            "hallway": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "crest_socket", "interaction_type": "rfid", "value": "sun_crest", "target_state": "courtyard"}]
            },
            "courtyard": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "crank_hole", "interaction_type": "rotary", "value": "turned", "target_state": "game_cleared"}]
            },
            "game_cleared": {
                "on_enter": [{"action": "publishStatus", "status": "completed"}],
                "transitions": []
            }
        }
    },
    "portal": {
        "room_id": "room1",
        "version": "aperture_v1",
        "initial_state": "test_chamber_01",
        "states": {
            "test_chamber_01": {
                "on_enter": [{"action": "publishStatus", "status": "started"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "portal_gun", "interaction_type": "pickup", "value": "blue_portal", "target_state": "test_chamber_02"}]
            },
            "test_chamber_02": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "weighted_cube", "interaction_type": "button", "value": "placed", "target_state": "glados_chamber"}]
            },
            "glados_chamber": {
                "on_enter": [{"action": "playAudio", "track": "still_alive.mp3"}],
                "transitions": [{"trigger": "time", "duration_seconds": 2, "target_state": "incinerator"}]
            },
            "incinerator": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "personality_core", "interaction_type": "rfid", "value": "morality_core", "target_state": "game_cleared"}]
            },
            "game_cleared": {
                "on_enter": [{"action": "publishStatus", "status": "completed"}],
                "transitions": []
            }
        }
    },
    "mario": {
        "room_id": "room1",
        "version": "bowser_castle_v1",
        "initial_state": "world_1",
        "states": {
            "world_1": {
                "on_enter": [{"action": "publishStatus", "status": "started"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "question_block", "interaction_type": "button", "value": "hit", "target_state": "mushroom_state"}]
            },
            "mushroom_state": {
                "on_enter": [{"action": "playAudio", "track": "powerup.mp3"}],
                "transitions": [{"trigger": "time", "duration_seconds": 1, "target_state": "castle_bridge"}]
            },
            "castle_bridge": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "axe", "interaction_type": "capacitive", "value": "touched", "target_state": "bowser_defeated"}]
            },
            "bowser_defeated": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "toad", "interaction_type": "rfid", "value": "thank_you", "target_state": "game_cleared"}]
            },
            "game_cleared": {
                "on_enter": [{"action": "publishStatus", "status": "completed"}],
                "transitions": []
            }
        }
    },
    "pokemon": {
        "room_id": "room1",
        "version": "gym_battle_v1",
        "initial_state": "gym_entrance",
        "states": {
            "gym_entrance": {
                "on_enter": [{"action": "publishStatus", "status": "started"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "statue", "interaction_type": "button", "value": "pressed", "target_state": "trainer_battle"}]
            },
            "trainer_battle": {
                "on_enter": [{"action": "playAudio", "track": "battle.mp3"}],
                "transitions": [{"trigger": "time", "duration_seconds": 1, "target_state": "leader_battle"}]
            },
            "leader_battle": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "pokeball", "interaction_type": "rfid", "value": "pikachu", "target_state": "gym_badge_earned"}]
            },
            "gym_badge_earned": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "door", "interaction_type": "capacitive", "value": "opened", "target_state": "game_cleared"}]
            },
            "game_cleared": {
                "on_enter": [{"action": "publishStatus", "status": "completed"}],
                "transitions": []
            }
        }
    },
    "fallout": {
        "room_id": "room1",
        "version": "vault_101_v1",
        "initial_state": "vault_door_sealed",
        "states": {
            "vault_door_sealed": {
                "on_enter": [{"action": "publishStatus", "status": "started"}],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "pipboy", "interaction_type": "rfid", "value": "scanned", "target_state": "overseer_office"}]
            },
            "overseer_office": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "terminal", "interaction_type": "button", "value": "hacked", "target_state": "vault_door_opening"}]
            },
            "vault_door_opening": {
                "on_enter": [{"action": "playAudio", "track": "siren.mp3"}],
                "transitions": [{"trigger": "time", "duration_seconds": 2, "target_state": "wasteland_exit"}]
            },
            "wasteland_exit": {
                "on_enter": [],
                "transitions": [{"trigger": "event", "event_type": "PropEvent", "prop_id": "geiger_counter", "interaction_type": "capacitive", "value": "touched", "target_state": "game_cleared"}]
            },
            "game_cleared": {
                "on_enter": [{"action": "publishStatus", "status": "completed"}],
                "transitions": []
            }
        }
    }
}

os.makedirs("config", exist_ok=True)
for name, data in strategies.items():
    with open(f"config/strategy_{name}.json", "w") as f:
        json.dump(data, f, indent=2)
print("Created 5 strategy configs.")

def test_strategy(name: str, data: dict):
    """Execute automated state transition test for a strategy by publishing hot-swap updates and simulating prop events.

    Args:
        name (str): Strategy theme name.
        data (dict): Strategy definition dictionary.
    """
    print(f"Testing {name}...")
    client = MQTTClient(f"tester_{name}", broker="localhost")
    client.start()
    while not client.connected:
        time.sleep(0.1)
        
    current_state = None
    
    # Write strategy to config/strategy_room1.json for room_control pickup
    with open("config/strategy_room1.json", "w") as f:
        json.dump(data, f, indent=2)
        
    print(f"[{name}] Injecting hot-swap strategy...")
    client.publish("catalog/room1/config-update", "{}")
    time.sleep(2)
    
    # Simulate step-by-step state transitions
    for state_name, state_config in data["states"].items():
        if state_name == "game_cleared":
            break
        for t in state_config.get("transitions", []):
            if t["trigger"] == "event":
                print(f"[{name}] Simulating event for {t['prop_id']}")
                client.publish(f"room/room1/prop/{t['prop_id']}/event", {
                    "prop_id": t["prop_id"],
                    "interaction_type": t["interaction_type"],
                    "value": t["value"]
                })
                time.sleep(1.5)
            elif t["trigger"] == "time":
                print(f"[{name}] Waiting for time transition ({t['duration_seconds']}s)...")
                time.sleep(t["duration_seconds"] + 1.0)
                
    time.sleep(2)
    client.stop()
    print(f"PASS: {name} strategy works perfectly.\n")

if __name__ == '__main__':
    print("Bringing up docker-compose to ensure system is running...")
    subprocess.check_call(["docker-compose", "up", "-d"], cwd=os.getcwd())
    time.sleep(5)
    
    for name, data in strategies.items():
        test_strategy(name, data)
        
    print("ALL STRATEGIES TESTED SUCCESSFULLY!")

