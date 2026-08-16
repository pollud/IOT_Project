"""Telegram Bot microservice providing interactive room control, status reporting, alert forwarding, and simulation execution via Telegram and REST webhook."""

import os
import time
import json
import threading
import cherrypy
import requests
from shared.mqtt import MQTTClient
from simulation_runner import run_live_simulation

class TelegramBot:
    """Telegram Bot and Webhook integration service for escape room remote monitoring and control."""

    def __init__(self):
        """Initialize TelegramBot, set up MQTT subscriptions, and launch Telegram polling thread if token is present."""
        self.broker = os.getenv("MQTT_BROKER", "mosquitto")
        self.token = os.getenv("TELEGRAM_TOKEN", "")
        
        self.cache = {
            "alerts": [],
            "status": {}
        }
        
        self.mqtt = MQTTClient(
            client_id="telegram_bot",
            broker=self.broker
        )
        self.mqtt.on_message_callback = self.on_message
        
        def run_mqtt():
            connected = False
            while not connected:
                try:
                    self.mqtt.start()
                    time.sleep(1)
                    if self.mqtt.connected:
                        connected = True
                    else:
                        self.mqtt.stop()
                        time.sleep(1)
                except Exception as e:
                    time.sleep(2)
            self.mqtt.subscribe("system/alerts")
            self.mqtt.subscribe("room/+/status")
            
        t = threading.Thread(target=run_mqtt, daemon=True)
        t.start()
        
        self.chat_ids = set()
        
        if self.token:
            self.telegram_url = f"https://api.telegram.org/bot{self.token}/"
            t2 = threading.Thread(target=self.poll_telegram, daemon=True)
            t2.start()
            
    def get_fancy_status(self) -> str:
        """Format current room status cache into a styled HTML Telegram message.

        Returns:
            str: HTML formatted status string.
        """
        if not self.cache["status"]:
            return "<i>No room status available yet.</i>"
        msg = "📊 <b>Escape Room Status</b>\n\n"
        for room_id, status in self.cache["status"].items():
            state = status.get("current_state", "Unknown")
            locked = not (state == "game_cleared")
            lock_emoji = "🔒 Locked" if locked else "🔓 Unlocked"
            msg += f"🚪 <b>{room_id.upper()}</b>\n"
            msg += f"  • State: <code>{state}</code>\n"
            msg += f"  • Door: {lock_emoji}\n\n"
        return msg

    def get_main_menu(self) -> dict:
        """Construct Telegram inline keyboard markup for interactive commands.

        Returns:
            dict: Reply markup dictionary for inline keyboard.
        """
        return {
            "inline_keyboard": [
                [{"text": "📊 Status", "callback_data": "status"}],
                [{"text": "🔓 Open Room 1", "callback_data": "open_room1"}, {"text": "🔓 Open Room 2", "callback_data": "open_room2"}],
                [{"text": "🔄 Reset Room 1", "callback_data": "reset_room1"}, {"text": "🔄 Reset Room 2", "callback_data": "reset_room2"}],
                [{"text": "🎮 Simulate Zelda (Room 1)", "callback_data": "simulate_zelda"}]
            ]
        }

    def send_telegram_message(self, chat_id, text: str, reply_markup=None):
        """Send HTML message with optional inline keyboard to target Telegram chat ID.

        Args:
            chat_id (str or int): Telegram chat ID.
            text (str): Message text.
            reply_markup (dict, optional): Keyboard markup dict.
        """
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            requests.post(self.telegram_url + "sendMessage", json=payload)
        except Exception:
            pass

    def answer_callback_query(self, callback_query_id: str, text: str = ""):
        """Acknowledge Telegram callback query from button press.

        Args:
            callback_query_id (str): Query ID.
            text (str): Toast notification text.
        """
        try:
            requests.post(self.telegram_url + "answerCallbackQuery", json={"callback_query_id": callback_query_id, "text": text})
        except Exception:
            pass

    def poll_telegram(self):
        """Long-polling thread loop fetching updates, commands, and callback queries from Telegram API."""
        last_update_id = 0
        while True:
            try:
                r = requests.get(self.telegram_url + f"getUpdates?offset={last_update_id}&timeout=10", timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("ok"):
                        for item in data.get("result", []):
                            last_update_id = item["update_id"] + 1
                            
                            # Handle Callback Queries (Button Presses)
                            if "callback_query" in item:
                                cb = item["callback_query"]
                                chat_id = cb["message"]["chat"]["id"]
                                data_str = cb["data"]
                                cb_id = cb["id"]
                                self.chat_ids.add(chat_id)
                                
                                if data_str == "status":
                                    self.send_telegram_message(chat_id, self.get_fancy_status(), self.get_main_menu())
                                    self.answer_callback_query(cb_id, "Status refreshed!")
                                elif data_str.startswith("open_"):
                                    room = data_str.split("_")[1]
                                    self.handle_command("/open", [room])
                                    self.send_telegram_message(chat_id, f"🔓 Opening {room}...", self.get_main_menu())
                                    self.answer_callback_query(cb_id, f"Opened {room}")
                                elif data_str.startswith("reset_"):
                                    room = data_str.split("_")[1]
                                    self.handle_command("/reset", [room])
                                    self.send_telegram_message(chat_id, f"🔄 Resetting {room}...", self.get_main_menu())
                                    self.answer_callback_query(cb_id, f"Reset {room}")
                                elif data_str == "simulate_zelda":
                                    self.answer_callback_query(cb_id, "Starting Zelda Simulation...")
                                    threading.Thread(target=self.run_zelda_simulation, args=(chat_id,), daemon=True).start()
                                else:
                                    self.answer_callback_query(cb_id)
                                    
                            # Handle standard Text Messages
                            elif "message" in item:
                                message = item["message"]
                                text = message.get("text", "")
                                chat_id = message.get("chat", {}).get("id")
                                if chat_id and text:
                                    self.chat_ids.add(chat_id)
                                    parts = text.split(" ")
                                    cmd = parts[0]
                                    args = parts[1:]
                                    
                                    if cmd in ["/start", "/help", "/menu"]:
                                        welcome = "👋 <b>Welcome to IoT Escape Room Control!</b>\nSelect an action below:"
                                        self.send_telegram_message(chat_id, welcome, self.get_main_menu())
                                    elif cmd == "/status":
                                        self.send_telegram_message(chat_id, self.get_fancy_status(), self.get_main_menu())
                                    elif cmd == "/simulate":
                                        if len(args) < 2:
                                            self.send_telegram_message(chat_id, "Usage: /simulate <room_id> <strategy_name>")
                                        else:
                                            run_live_simulation(args[0], args[1], self.mqtt, self, chat_id)
                                    else:
                                        # Fallback to standard handler for other commands
                                        reply = self.handle_command(cmd, args)
                                        self.send_telegram_message(chat_id, reply)
            except Exception as e:
                pass
            time.sleep(1)
        
    def on_message(self, topic: str, payload):
        """Process incoming MQTT messages for room status updates and system alerts, broadcasting alerts to subscribed chats.

        Args:
            topic (str): MQTT topic.
            payload (Any): Payload object or JSON string.
        """
        try:
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8')
            elif isinstance(payload, dict):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)
                
            data = json.loads(payload_str)
            if "status" in topic:
                room_id = topic.split("/")[1]
                self.cache["status"][room_id] = data
            elif "alerts" in topic:
                self.cache["alerts"].append(data)
                alert_text = f"🚨 <b>ALERT</b>\n<code>{json.dumps(data, indent=2)}</code>"
                if self.token:
                    for chat_id in self.cache.get("subscribed_chats", list(self.chat_ids)):
                        self.send_telegram_message(chat_id, alert_text)
        except Exception as e:
            pass
            
    def run_zelda_simulation(self, chat_id):
        """Run step-by-step interactive Zelda theme room simulation, publishing prop triggers and sending progress messages to Telegram.

        Args:
            chat_id (str or int): Target chat ID for notifications.
        """
        self.send_telegram_message(chat_id, "🎮 <b>Simulation Started</b>: Zelda Dungeon (Room 1)\n\n<i>Pressing 'switch_1' button...</i>")
        self.mqtt.publish("game/room1/prop/switch_1/interaction", {"prop_id": "switch_1", "interaction_type": "button", "value": "pressed"})
        time.sleep(4) # wait for time trigger (3s) to pass hint_needed
        
        self.send_telegram_message(chat_id, "<i>Scanning 'triforce_key' on boss_key_reader...</i>")
        self.mqtt.publish("game/room1/prop/boss_key_reader/interaction", {"prop_id": "boss_key_reader", "interaction_type": "rfid", "value": "triforce_key"})
        time.sleep(2)
        
        self.send_telegram_message(chat_id, "<i>Touching the 'master_sword'...</i>")
        self.mqtt.publish("game/room1/prop/master_sword/interaction", {"prop_id": "master_sword", "interaction_type": "capacitive", "value": "touched"})
        time.sleep(2)
        
        self.send_telegram_message(chat_id, "✅ <b>Simulation Complete!</b> Check /status to see the door unlocked (game_cleared).")
            
    def handle_command(self, cmd: str, args: list) -> str:
        """Process command string (/status, /open, /reset, /simulate, /help) and perform corresponding actions.

        Args:
            cmd (str): Command name.
            args (list): List of command arguments.

        Returns:
            str: Resulting text response message.
        """
        if cmd == "/status":
            return json.dumps(self.cache["status"])
        elif cmd == "/open":
            room_id = args[0] if args else "room1"
            self.mqtt.publish(f"command/room/{room_id}", {"room_id": room_id, "command": "unlockDoor"})
            return f"Opening {room_id}"
        elif cmd == "/reset":
            room_id = args[0] if args else "room1"
            self.mqtt.publish(f"command/room/{room_id}", {"room_id": room_id, "command": "reset"})
            return f"Resetting {room_id}"
        elif cmd == "/simulate":
            if len(args) < 2:
                return "Usage: /simulate <room_id> <strategy_name>"
            from simulation_runner import run_live_simulation
            run_live_simulation(args[0], args[1], self.mqtt, self, "system")
            return f"Started simulation for {args[0]} with {args[1]}"
        elif cmd == "/help":
            return "/status, /open <room>, /reset <room>, /simulate <room> <strategy>"
        return "Unknown command"
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def webhook(self):
        """POST /webhook CherryPy HTTP REST endpoint for processing incoming bot webhook requests."""
        data = cherrypy.request.json
        text = data.get("message", {}).get("text", "")
        parts = text.split(" ")
        cmd = parts[0]
        args = parts[1:]
        
        start_time = time.time()
        
        chat_id = data.get("message", {}).get("chat", {}).get("id")
        if cmd == "/simulate":
            if len(args) < 2:
                reply = "Usage: /simulate <room_id> <strategy_name>"
            else:
                from simulation_runner import run_live_simulation
                run_live_simulation(args[0], args[1], self.mqtt, self, chat_id or "system")
                reply = f"Started simulation for {args[0]} with {args[1]}"
        else:
            reply = self.handle_command(cmd, args)
            
        duration = time.time() - start_time
        
        return {"reply": reply, "duration": duration}

if __name__ == "__main__":
    bot = TelegramBot()
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8086,
    })
    cherrypy.quickstart(bot)

