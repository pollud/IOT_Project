"""Multi-room game center simulation engine generating environment telemetry, player badge coordinates, puzzle prop triggers, and requesting analytics reports across 10 theme rooms."""

import json
import time
import random
import threading
import requests
import os
import sys
from shared.mqtt import MQTTClient

#: List of 10 supported theme room IDs in the game center.
ROOMS = [
    "room_cyberpunk",
    "room_matrix",
    "room_alien",
    "room_dungeon",
    "room_atlantis",
    "room_tomb",
    "room_haunted",
    "room_asylum",
    "room_sherlock",
    "room_arcade"
]

#: Mapping of room IDs to strategy configuration names.
STRATEGIES = {
    "room_cyberpunk": "cyberpunk",
    "room_matrix": "matrix",
    "room_alien": "alien",
    "room_dungeon": "dungeon",
    "room_atlantis": "atlantis",
    "room_tomb": "tomb",
    "room_haunted": "haunted",
    "room_asylum": "asylum",
    "room_sherlock": "sherlock",
    "room_arcade": "arcade"
}

def load_strategy(strat_name: str) -> dict:
    """Load strategy JSON configuration for given strategy name from config directory.

    Args:
        strat_name (str): Name of strategy file.

    Returns:
        dict: Parsed strategy dictionary.
    """
    filepath = f"config/strategy_{strat_name}.json"
    with open(filepath, "r") as f:
        return json.load(f)

client = MQTTClient("game_center_simulator_master", broker="localhost")

def environment_and_badge_publisher(stop_event: threading.Event):
    """Publish continuous high-frequency environmental telemetry (temp, humidity, CO2, noise) and player badge telemetry (position, battery) across all 10 rooms.

    Args:
        stop_event (threading.Event): Thread stop signal event.
    """
    print("🚀 Telemetry Publisher Thread started across all 10 game rooms...")
    while not stop_event.is_set():
        for i, room_id in enumerate(ROOMS):
            # 1. Environment Telemetry (Temp, Humidity, CO2, Noise dBA)
            temp = 21.0 + random.uniform(-2, 3)
            hum = 45.0 + random.uniform(-5, 5)
            co2_ppm = 400 + random.randint(0, 150)
            noise_dba = 55 + random.randint(0, 30)
            
            client.publish(f"room/{room_id}/environment", {
                "temperature": temp,
                "humidity": hum,
                "co2_ppm": co2_ppm,
                "noise_dba": noise_dba
            }, qos=0)

            # 2. Player Badge Telemetry (Position, Heart Rate, Battery)
            badge_id = f"badge_{room_id}_p1"
            x_pos = round(random.uniform(0, 10), 1)
            y_pos = round(random.uniform(0, 10), 1)
            heart_rate = 75 + random.randint(0, 35)
            battery = max(10.0, 100.0 - (random.random() * 5.0))

            client.publish(f"room/{room_id}/badge/{badge_id}/position", {
                "badge_id": badge_id,
                "x": x_pos,
                "y": y_pos,
                "zone": "puzzle_area"
            }, qos=0)

            client.publish(f"room/{room_id}/badge/{badge_id}/battery", {
                "badge_id": badge_id,
                "battery_level": battery
            }, qos=0)

        time.sleep(0.5)

def run_room_simulation(room_id: str, strat_name: str, badge_id: str):
    """Simulate a complete escape room game session for a room by stepping through FSM transitions.

    Args:
        room_id (str): Target room ID.
        strat_name (str): Strategy configuration name.
        badge_id (str): Player badge ID.
    """
    data = load_strategy(strat_name)
    print(f"🎮 [{room_id}] Starting Game: '{data.get('name')}'")

    # Hot-swap config update publication
    client.publish(f"catalog/{room_id}/config-update", {"room_id": room_id, "version": data.get("version")}, qos=1, retain=True)
    time.sleep(0.5)

    # Publish initial entrance position
    client.publish(f"room/{room_id}/badge/{badge_id}/position", {"badge_id": badge_id, "x": 0.5, "y": 0.5, "zone": "entrance"}, qos=0)
    time.sleep(0.5)

    states = data.get("states", {})
    for state_name, state_config in states.items():
        if state_name in ("core_unlocked", "mainframes_accessible", "escape_pod_ready", "gate_unlocked", "temple_sealed", "tomb_opened", "curse_lifted", "patient_escaped", "case_solved", "champion_cleared"):
            break

        transitions = state_config.get("transitions", [])
        for t in transitions:
            if t.get("trigger") == "event":
                client.publish(f"room/{room_id}/badge/{badge_id}/position", {
                    "badge_id": badge_id,
                    "x": random.uniform(2, 8),
                    "y": random.uniform(2, 8),
                    "zone": state_name
                }, qos=0)
                time.sleep(0.3)

                prop_id = t.get("prop_id")
                interaction_type = t.get("interaction_type")
                val = t.get("value")

                print(f"  👉 [{room_id}] Triggering prop '{prop_id}' ({interaction_type}={val})")
                client.publish(f"room/{room_id}/prop/{prop_id}/event", {
                    "prop_id": prop_id,
                    "interaction_type": interaction_type,
                    "value": val
                }, qos=1)
                time.sleep(0.8)

    duration = random.randint(1800, 3200)
    print(f"🏆 [{room_id}] Completed '{data.get('name')}' in {duration}s!")
    client.publish(f"game/{room_id}/session/ended", {
        "room_id": room_id,
        "duration": duration,
        "status": "won"
    }, qos=1)
    time.sleep(0.5)

def main():
    """Main execution entry point initializing MQTT client, running parallel room simulations, and querying analytics reports."""
    print("=" * 70)
    print("🏢 MEGA IOT GAME CENTER - SIMULATION ENGINE")
    print("=" * 70)
    print("Connecting to MQTT broker...")
    
    client.start()
    for _ in range(50):
        if client.connected:
            break
        time.sleep(0.1)

    if not client.connected:
        print("❌ Error: Could not connect to Mosquitto MQTT broker at localhost:1883!")
        sys.exit(1)

    print("✅ Connected to MQTT broker.")

    stop_telemetry = threading.Event()
    telemetry_thread = threading.Thread(target=environment_and_badge_publisher, args=(stop_telemetry,), daemon=True)
    telemetry_thread.start()

    print("\n▶️ Launching parallel escape room sessions across all 10 rooms...")
    threads = []
    for room_id in ROOMS:
        strat_name = STRATEGIES[room_id]
        badge_id = f"b_{room_id}"
        t = threading.Thread(target=run_room_simulation, args=(room_id, strat_name, badge_id))
        threads.append(t)
        t.start()
        time.sleep(0.2)

    for t in threads:
        t.join()

    print("\n⏹ Stopping telemetry stream...")
    stop_telemetry.set()
    telemetry_thread.join(timeout=2)
    client.stop()

    print("\n" + "=" * 70)
    print("📊 ADVANCED DATA PROCESSING & ANALYTICS REPORT")
    print("=" * 70)

    time.sleep(1)

    # 1. Query Center Overview
    try:
        r = requests.get("http://localhost:8084/stats/game_center", timeout=5).json()
        print("\n🏛️ 1. GAME CENTER OVERVIEW:")
        print(json.dumps(r, indent=2))
    except Exception as e:
        print("Failed to fetch Game Center overview", e)

    # 2. Query Bottlenecks & Chokepoint Analysis
    try:
        r = requests.get("http://localhost:8084/stats/bottlenecks", timeout=5).json()
        print("\n🔍 2. PUZZLE BOTTLENECK & CHOKEPOINT ANALYTICS:")
        print(json.dumps(r, indent=2))
    except Exception as e:
        print("Failed to fetch Bottleneck analytics", e)

    # 3. Query Safety & Physical Strain Index
    try:
        r = requests.get("http://localhost:8084/stats/safety", timeout=5).json()
        print("\n❤️ 3. PLAYER SAFETY & COMFORT INDEX:")
        print(json.dumps(r, indent=2))
    except Exception as e:
        print("Failed to fetch Safety index", e)

    # 4. Query Hardware Maintenance Diagnostics
    try:
        r = requests.get("http://localhost:8084/stats/maintenance", timeout=5).json()
        print("\n🛠️ 4. HARDWARE MAINTENANCE DIAGNOSTICS:")
        print(json.dumps(r, indent=2))
    except Exception as e:
        print("Failed to fetch Maintenance diagnostics", e)

    # 5. Query Spatial Heatmap Sample
    try:
        r = requests.get("http://localhost:8084/stats/heatmap/room_cyberpunk", timeout=5).json()
        print("\n🗺️ 5. PLAYER SPATIAL HEATMAP (sample: room_cyberpunk):")
        print(json.dumps(r, indent=2))
    except Exception as e:
        print("Failed to fetch Heatmap", e)

    print("\n" + "=" * 70)
    print("🎉 Game Center Simulation Complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()

