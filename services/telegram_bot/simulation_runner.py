import json
import time
import threading

def run_live_simulation(room_id, strategy_name, mqtt_client, bot, chat_id):
    def simulation_thread():
        try:
            bot.send_telegram_message(chat_id=chat_id, text=f"🎮 Starting LIVE simulation for {room_id} with strategy: {strategy_name}")
            
            with open(f"/app/config/strategy_{strategy_name}.json", "r") as f:
                data = json.load(f)
            data["room_id"] = room_id
            
            # Write strategy to local config (triggers config-update)
            with open(f"/app/config/strategy_{room_id}.json", "w") as f:
                json.dump(data, f, indent=2)
                
            mqtt_client.publish(f"catalog/{room_id}/config-update", "{}")
            bot.send_telegram_message(chat_id=chat_id, text=f"⚙️ Loaded {strategy_name} into {room_id}. Waiting for FSM to restart...")
            time.sleep(3)
            
            badge_id = "b1" if room_id == "room1" else "b2"
            mqtt_client.publish(f"game/{room_id}/badge/{badge_id}/position", {"zone": "entrance"})
            
            for state_name, state_config in data["states"].items():
                if state_name == "game_cleared":
                    break
                for t in state_config.get("transitions", []):
                    if t["trigger"] == "event":
                        bot.send_telegram_message(chat_id=chat_id, text=f"🔍 Exploring... Player moving to zone: {state_name}")
                        mqtt_client.publish(f"game/{room_id}/badge/{badge_id}/position", {"zone": state_name})
                        time.sleep(2)
                        
                        bot.send_telegram_message(chat_id=chat_id, text=f"⚡ Triggering prop: {t['prop_id']} ({t['interaction_type']} = {t['value']})")
                        mqtt_client.publish(f"game/{room_id}/prop/{t['prop_id']}/interaction", {
                            "prop_id": t["prop_id"],
                            "interaction_type": t["interaction_type"],
                            "value": t["value"]
                        })
                        
                        # Wait long enough for the dashboard to visibly update and teacher to see it
                        time.sleep(5)
                        
                    elif t["trigger"] == "time":
                        bot.send_telegram_message(chat_id=chat_id, text=f"⏳ Waiting for {t['duration_seconds']}s time transition...")
                        time.sleep(t["duration_seconds"] + 1)
                        
            bot.send_telegram_message(chat_id=chat_id, text=f"✅ Simulation for {room_id} finished. Room should now be unlocked on the dashboard!")
            mqtt_client.publish(f"game/{room_id}/session/ended", {"room_id": room_id, "duration": 2500, "status": "won"})
            
        except Exception as e:
            try:
                bot.send_telegram_message(chat_id=chat_id, text=f"❌ Simulation error: {str(e)}")
            except Exception:
                pass

    t = threading.Thread(target=simulation_thread, daemon=True)
    t.start()
