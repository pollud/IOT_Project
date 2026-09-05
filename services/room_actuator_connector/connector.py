"""Room Actuator Device Connector for locks, lights and audio outputs."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any

import cherrypy

from shared.catalog_client import CatalogClient
from shared.config import validate_identifier
from shared.http import server_config
from shared.mqtt import MQTTClient
from shared.topics import emergency_command, room_command

LOGGER = logging.getLogger("room_actuator_connector")


class ActuatorBank:
    """Thread-safe simulated relay/audio/light hardware abstraction."""

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.lock = threading.RLock()
        self.state: dict[str, Any] = {"door_locked": True, "light_color": "off", "audio_track": None}
        self.log: deque[dict[str, Any]] = deque(maxlen=100)

    def execute(self, command: str, parameters: dict[str, Any], source: str) -> dict[str, Any]:
        aliases = {"unlockDoor": "unlock", "lockDoor": "lock", "playAudio": "play_audio", "setLights": "set_lights"}
        command = aliases.get(command, command)
        with self.lock:
            if command == "unlock":
                self.state["door_locked"] = False
            elif command == "lock":
                self.state["door_locked"] = True
            elif command == "set_lights":
                color = str(parameters.get("color", "")).strip()
                if not color:
                    raise ValueError("set_lights requires parameters.color")
                self.state["light_color"] = color
            elif command == "play_audio":
                track = str(parameters.get("track", "")).strip()
                if not track:
                    raise ValueError("play_audio requires parameters.track")
                self.state["audio_track"] = track
            elif command in {"reset", "start"}:
                return dict(self.state)
            else:
                raise ValueError(f"Unsupported actuator command: {command}")
            entry = {
                "timestamp": time.time(),
                "command": command,
                "parameters": dict(parameters),
                "source": source,
                "state": dict(self.state),
            }
            self.log.append(entry)
            LOGGER.info("[%s] %s", self.room_id, entry)
            return dict(self.state)


class RoomActuatorConnector:
    def __init__(self, room_id: str, catalog: CatalogClient) -> None:
        self.room_id = validate_identifier(room_id, "room_id")
        self.catalog = catalog
        self.bank = ActuatorBank(self.room_id)
        self.mqtt = MQTTClient(
            f"room_actuator_connector_{self.room_id}",
            heartbeat_payload=lambda: {"room_id": self.room_id, **self.bank.state},
        )
        self.mqtt.on_message_callback = self.on_message

    def start(self) -> None:
        self.catalog.room(self.room_id)
        self.catalog.register_service(
            name=f"room_actuator_connector_{self.room_id}",
            description="Mag-lock, lighting and audio actuator connector",
            endpoint=os.getenv("SERVICE_URL", f"http://room_actuator_connector_{self.room_id}:8082"),
            room_id=self.room_id,
            mqtt_topics=[room_command(self.room_id), emergency_command(self.room_id)],
        )
        self.catalog.register_device(
            device_id=f"actuator_{self.room_id}",
            kind="room_actuator_bank",
            room_id=self.room_id,
            connector=f"room_actuator_connector_{self.room_id}",
            metadata={"actuators": ["main_door", "lights", "audio"]},
        )
        self.mqtt.subscribe(room_command(self.room_id), qos=1)
        self.mqtt.subscribe(emergency_command(self.room_id), qos=1)
        self.mqtt.start()

    def stop(self) -> None:
        self.mqtt.stop()

    def on_message(self, topic: str, payload: str) -> None:
        if topic not in {room_command(self.room_id), emergency_command(self.room_id)}:
            LOGGER.debug("Ignored unrelated MQTT topic: %s", topic)
            return
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise TypeError("Actuator payload must be a JSON object")
            if topic == emergency_command(self.room_id):
                self.bank.execute("unlock", {}, "safety_monitor")
                self.bank.execute("set_lights", {"color": "emergency_white"}, "safety_monitor")
                self.bank.execute("play_audio", {"track": "evacuation_alarm.mp3"}, "safety_monitor")
                return
            if data.get("room_id") != self.room_id:
                return
            parameters = data.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise TypeError("parameters must be a JSON object")
            self.bank.execute(
                str(data.get("command", "")),
                dict(parameters),
                str(data.get("issued_by", "unknown")),
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            LOGGER.exception("Rejected actuator command on %s", topic)


class Root:
    def __init__(self, connector: RoomActuatorConnector) -> None:
        self.connector = connector

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok" if self.connector.mqtt.connected else "degraded",
            "room_id": self.connector.room_id,
            "actuators": dict(self.connector.bank.state),
            "recent_commands": list(self.connector.bank.log),
        }


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    connector = RoomActuatorConnector(os.getenv("ROOM_ID", "room1"), catalog)
    connector.start()
    cherrypy.engine.subscribe("stop", connector.stop)
    cherrypy.config.update(server_config(8082))
    cherrypy.quickstart(Root(connector))


if __name__ == "__main__":
    main()
