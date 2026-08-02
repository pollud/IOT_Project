import json
import time
import random
import threading
import requests
from shared.mqtt import MQTTClient
import os

strategies = ["resident_evil", "portal", "mario", "pokemon", "fallout"]

def load_strategy(name):
    with open(f"config/strategy_{name}.json", "r") as f:
        return json.loads(f.read())

client = MQTTClient("simulator_master", broker="localhost")

def environment_publisher():
    t = threading.currentThread()
    while getattr(t, "do_run", True):
        temp = 20.0 + random.uniform(-2, 2)
        hum = 45.0 + random.uniform(-5, 5)
        client.publish("room/room1/environment", {"temperature": temp, "humidity": hum})
        client.publish("room/room2/environment", {"temperature": temp + 2, "humidity": hum + 5})
        time.sleep(1)

def run_simulation(room_id, strategy_name, badge_id):
    print(f"Starting simulation for {room_id} with strategy {strategy_name}")
    data = load_strategy(strategy_name)
    data["room_id"] = room_id
    
    # Write to config so it reloads locally
    with open(f"config/strategy_{room_id}.json", "w") as f:
        json.dump(data, f, indent=2)
        
    client.publish(f"catalog/{room_id}/config-update", "{}")
    time.sleep(2)
    
    client.publish(f"room/{room_id}/badge/{badge_id}/position", {"zone": "entrance"})
    time.sleep(1)
    
    for state_name, state_config in data["states"].items():
        if state_name == "game_cleared":
            break
        for t in state_config.get("transitions", []):
            if t["trigger"] == "event":
                client.publish(f"room/{room_id}/badge/{badge_id}/position", {"zone": state_name})
                time.sleep(0.5)
                print(f"[{room_id}] Triggering {t['prop_id']}")
                client.publish(f"room/{room_id}/prop/{t['prop_id']}/event", {
                    "prop_id": t["prop_id"],
                    "interaction_type": t["interaction_type"],
                    "value": t["value"]
                })
                time.sleep(1.5)
            elif t["trigger"] == "time":
                print(f"[{room_id}] Waiting {t['duration_seconds']}s")
                time.sleep(t["duration_seconds"] + 0.5)
                
    duration = random.randint(1800, 3600)
    print(f"[{room_id}] Finished in {duration}s")
    client.publish(f"game/{room_id}/session/ended", {"room_id": room_id, "duration": duration, "status": "won"})
    time.sleep(1)

if __name__ == "__main__":
    import subprocess
    print("Ensuring system is up...")
    subprocess.check_call(["docker-compose", "up", "-d"])
    time.sleep(3)
    
    client.start()
    while not client.connected:
        time.sleep(0.1)
        
    env_thread = threading.Thread(target=environment_publisher)
    env_thread.do_run = True
    env_thread.start()
    
    for i, strat in enumerate(strategies):
        # Run sequentially on room1 and room2
        strat_2 = strategies[(i+1) % len(strategies)]
        run_simulation("room1", strat, "b1")
        run_simulation("room2", strat_2, "b2")
        time.sleep(2)
        
    env_thread.do_run = False
    env_thread.join()
    client.stop()
    
    print("--------------------------------------------------")
    print("Simulations complete. Databases and Analytics populated.")
    print("--------------------------------------------------")
    print("Fetching Analytics for room1:")
    try:
        r1 = requests.get("http://localhost:8084/stats/room/room1")
        print(json.dumps(r1.json(), indent=2))
    except Exception as e:
        print("Failed to get room1 stats", e)
        
    print("\nFetching Analytics for room2:")
    try:
        r2 = requests.get("http://localhost:8084/stats/room/room2")
        print(json.dumps(r2.json(), indent=2))
    except Exception as e:
        print("Failed to get room2 stats", e)
