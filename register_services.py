import requests

catalog_url = "http://localhost:8080/register"

services = [
    {"type": "service", "name": "room_control", "description": "Room FSM Controller"},
    {"type": "service", "name": "timeseries_adapter", "description": "Telemetry Persistence DB"},
    {"type": "service", "name": "analytics", "description": "Analytics Engine", "endpoint": "http://analytics:8084"},
    {"type": "service", "name": "telegram_bot", "description": "Telegram Alerting Bot"},
    {"type": "service", "name": "safety_monitor", "description": "Safety Monitor Rules Engine"},
    {"type": "service", "name": "thingspeak_adapter", "description": "ThingSpeak Sync", "endpoint": "http://thingspeak_adapter:8085"},
    {"type": "service", "name": "web_dashboard", "description": "Game Master Command Center Web UI", "endpoint": "http://web_dashboard:8087"}
]

devices = [
    {"type": "device", "device_id": "room_room1", "room_id": "room1", "description": "Room 1 Env Sensors"},
    {"type": "device", "device_id": "room_room2", "room_id": "room2", "description": "Room 2 Env Sensors"},
    {"type": "device", "device_id": "badge_b1", "room_id": "room1", "description": "Player 1 Badge Simulator"},
    {"type": "device", "device_id": "badge_b2", "room_id": "room2", "description": "Player 2 Badge Simulator"},
    {"type": "device", "device_id": "prop_prop1", "room_id": "room1", "description": "Prop Simulator 1"},
    {"type": "device", "device_id": "prop_prop2", "room_id": "room2", "description": "Prop Simulator 2"}
]

for s in services:
    requests.post(catalog_url, json=s)
    
for d in devices:
    requests.post(catalog_url, json=d)

print("Registered everything!")
