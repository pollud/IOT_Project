"""Badge Device Connector: positioning, battery, heartbeat and fall detection."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import cherrypy

from shared.catalog_client import CatalogClient
from shared.config import env_float, validate_identifier
from shared.http import server_config
from shared.mqtt import MQTTClient
from shared.senml import make_pack
from shared.topics import badge

LOGGER = logging.getLogger("badge_connector")


@dataclass
class BadgeState:
    badge_id: str
    player: str
    x: float
    y: float
    battery: float = 100.0


class BadgeConnector:
    def __init__(self, room_id: str, catalog: CatalogClient) -> None:
        self.room_id = validate_identifier(room_id, "room_id")
        self.catalog = catalog
        room = catalog.room(self.room_id)
        dimensions = room["dimensions"]
        self.width = float(dimensions["width_m"])
        self.height = float(dimensions["height_m"])
        self.interval = env_float("PUBLISH_INTERVAL", 2.0, minimum=0.2)
        # Deterministic simulation data; this generator is never used for security.
        self.random = random.Random(f"badge:{self.room_id}")  # nosec B311
        self.badges: dict[str, BadgeState] = {}
        for index, definition in enumerate(room["badges"]):
            badge_id = validate_identifier(definition["badge_id"], "badge_id")
            self.badges[badge_id] = BadgeState(
                badge_id=badge_id,
                player=str(definition.get("player", badge_id)),
                x=min(self.width, 1.0 + index),
                y=min(self.height, 1.0 + index),
            )
        if not self.badges:
            raise ValueError(f"Room {self.room_id} has no configured badges")
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.mqtt = MQTTClient(
            f"badge_connector_{self.room_id}",
            heartbeat_payload=lambda: {
                "room_id": self.room_id,
                "badges_active": len(self.badges),
                "badges_total": len(self.badges),
            },
        )

    def start(self) -> None:
        service_name = f"badge_connector_{self.room_id}"
        self.catalog.register_service(
            name=service_name,
            description="ESP32 badge positioning and safety connector",
            endpoint=os.getenv("SERVICE_URL", f"http://{service_name}:8083"),
            room_id=self.room_id,
            mqtt_topics=[f"game/{self.room_id}/badge/+/+"],
        )
        for state in self.badges.values():
            self.catalog.register_device(
                device_id=state.badge_id,
                kind="player_badge",
                room_id=self.room_id,
                connector=service_name,
                metadata={"player": state.player, "sensors": ["uwb_position", "accelerometer", "battery"]},
            )
        self.mqtt.start()
        self._thread = threading.Thread(target=self._simulation_loop, name=f"badges-{self.room_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.mqtt.stop()

    def _move(self, state: BadgeState) -> None:
        state.x = min(self.width, max(0.0, state.x + self.random.uniform(-0.45, 0.45)))
        state.y = min(self.height, max(0.0, state.y + self.random.uniform(-0.45, 0.45)))
        state.battery = max(0.0, state.battery - self.random.uniform(0.002, 0.015))

    def publish_badge(self, state: BadgeState) -> None:
        now = time.time()
        base = f"urn:escape-room:{self.room_id}:badge:{state.badge_id}:"
        self.mqtt.publish(
            badge(self.room_id, state.badge_id, "position"),
            make_pack(base, [("x", round(state.x, 3), "m"), ("y", round(state.y, 3), "m")], now),
            qos=0,
        )
        self.mqtt.publish(
            badge(self.room_id, state.badge_id, "battery"),
            make_pack(base, [("battery", round(state.battery, 2), "%")], now),
            qos=0,
        )
        self.mqtt.publish(
            badge(self.room_id, state.badge_id, "heartbeat"),
            make_pack(base, [("online", True, None)], now),
            qos=0,
        )

    def _simulation_loop(self) -> None:
        while not self._stop.is_set():
            with self.lock:
                states = list(self.badges.values())
                for state in states:
                    self._move(state)
                    try:
                        self.publish_badge(state)
                    except RuntimeError:
                        LOGGER.warning("Badge telemetry paused while MQTT is disconnected")
                        break
                    except Exception:
                        LOGGER.exception("Badge telemetry failed for %s", state.badge_id)
            self._stop.wait(self.interval)

    def force_fall(self, badge_id: str) -> None:
        badge_id = validate_identifier(badge_id, "badge_id")
        if badge_id not in self.badges:
            raise KeyError(badge_id)
        self.mqtt.publish(
            badge(self.room_id, badge_id, "safety"),
            make_pack(
                f"urn:escape-room:{self.room_id}:badge:{badge_id}:",
                [("fall_detected", True, None), ("peak_acceleration", 2.8, "g")],
            ),
            qos=1,
            wait=True,
        )

    def battery_snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                {"badge_id": state.badge_id, "player": state.player, "battery_percent": round(state.battery, 2)}
                for state in self.badges.values()
            ]


class Root:
    def __init__(self, connector: BadgeConnector) -> None:
        self.connector = connector

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok" if self.connector.mqtt.connected else "degraded",
            "room_id": self.connector.room_id,
            "badges": self.connector.battery_snapshot(),
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def battery(self, badge_id: str | None = None):
        if cherrypy.request.method.upper() != "GET":
            raise cherrypy.HTTPError(405, "GET required")
        records = self.connector.battery_snapshot()
        if badge_id:
            records = [record for record in records if record["badge_id"] == badge_id]
            if not records:
                raise cherrypy.HTTPError(404, f"Unknown badge: {badge_id}")
        return {"room_id": self.connector.room_id, "badges": records}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def force_fall(self, badge_id: str | None = None):
        if cherrypy.request.method.upper() != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        selected = badge_id or next(iter(self.connector.badges))
        try:
            self.connector.force_fall(selected)
        except KeyError as error:
            raise cherrypy.HTTPError(404, f"Unknown badge: {error.args[0]}") from error
        except ValueError as error:
            raise cherrypy.HTTPError(400, str(error)) from error
        return {"status": "published", "room_id": self.connector.room_id, "badge_id": selected}


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    connector = BadgeConnector(os.getenv("ROOM_ID", "room1"), catalog)
    connector.start()
    cherrypy.engine.subscribe("stop", connector.stop)
    cherrypy.config.update(server_config(8083))
    cherrypy.quickstart(Root(connector))


if __name__ == "__main__":
    main()
