"""Prop Device Connector for RFID, capacitive, button and rotary sensors."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

import cherrypy

from shared.catalog_client import CatalogClient
from shared.config import env_float, validate_identifier
from shared.http import server_config
from shared.mqtt import MQTTClient
from shared.senml import make_pack
from shared.topics import prop

LOGGER = logging.getLogger("prop_connector")


def read_json_body() -> dict[str, Any]:
    if "application/json" not in cherrypy.request.headers.get("Content-Type", ""):
        raise cherrypy.HTTPError(415, "Content-Type must be application/json")
    try:
        data = json.loads(cherrypy.request.body.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise cherrypy.HTTPError(400, f"Invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise cherrypy.HTTPError(400, "JSON body must be an object")
    return data


class PropConnector:
    def __init__(self, room_id: str, catalog: CatalogClient) -> None:
        self.room_id = validate_identifier(room_id, "room_id")
        self.catalog = catalog
        room = catalog.room(self.room_id)
        self.props: dict[str, dict[str, Any]] = {
            validate_identifier(item["prop_id"], "prop_id"): dict(item) for item in room["props"]
        }
        if not self.props:
            raise ValueError(f"Room {self.room_id} has no configured props")
        self.interval = env_float("HEALTH_INTERVAL", 5.0, minimum=0.5)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_interaction: dict[str, float] = {}
        self.mqtt = MQTTClient(
            f"prop_connector_{self.room_id}",
            heartbeat_payload=lambda: {
                "room_id": self.room_id,
                "props_online": len(self.props),
                "props_total": len(self.props),
            },
        )

    def start(self) -> None:
        service_name = f"prop_connector_{self.room_id}"
        self.catalog.register_service(
            name=service_name,
            description="Interactive prop RFID/capacitive/button connector",
            endpoint=os.getenv("SERVICE_URL", f"http://{service_name}:8084"),
            room_id=self.room_id,
            mqtt_topics=[f"game/{self.room_id}/prop/+/+"],
        )
        for prop_id, definition in self.props.items():
            self.catalog.register_device(
                device_id=prop_id,
                kind="interactive_prop",
                room_id=self.room_id,
                connector=service_name,
                metadata={"sensor": definition["sensor"], "expected_value": definition.get("expected_value")},
            )
        self.mqtt.start()
        self._thread = threading.Thread(target=self._health_loop, name=f"props-{self.room_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.mqtt.stop()

    def _health_loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            for prop_id in self.props:
                base = f"urn:escape-room:{self.room_id}:prop:{prop_id}:"
                try:
                    self.mqtt.publish(
                        prop(self.room_id, prop_id, "health"),
                        make_pack(base, [("online", True, None), ("signal_strength", -55.0, "dBm")], now),
                        qos=0,
                    )
                    self.mqtt.publish(
                        prop(self.room_id, prop_id, "heartbeat"),
                        make_pack(base, [("online", True, None)], now),
                        qos=0,
                    )
                except RuntimeError:
                    LOGGER.warning("Prop health paused while MQTT is disconnected")
                    break
                except Exception:
                    LOGGER.exception("Prop health failed for %s", prop_id)
            self._stop.wait(self.interval)

    def trigger(self, prop_id: str, interaction_type: str, value: str) -> None:
        prop_id = validate_identifier(prop_id, "prop_id")
        if prop_id not in self.props:
            raise KeyError(prop_id)
        expected_type = str(self.props[prop_id]["sensor"])
        if interaction_type != expected_type:
            raise ValueError(f"Prop {prop_id} expects interaction_type={expected_type}")
        now = time.time()
        self.last_interaction[prop_id] = now
        self.mqtt.publish(
            prop(self.room_id, prop_id, "interaction"),
            make_pack(
                f"urn:escape-room:{self.room_id}:prop:{prop_id}:",
                [("interaction_type", interaction_type, None), ("value", str(value), None)],
                now,
            ),
            qos=1,
            wait=True,
        )


class Root:
    def __init__(self, connector: PropConnector) -> None:
        self.connector = connector

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok" if self.connector.mqtt.connected else "degraded",
            "room_id": self.connector.room_id,
            "props": [
                {**definition, "last_interaction": self.connector.last_interaction.get(prop_id)}
                for prop_id, definition in self.connector.props.items()
            ],
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def trigger(self):
        if cherrypy.request.method.upper() != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        data = read_json_body()
        try:
            self.connector.trigger(
                str(data.get("prop_id", "")),
                str(data.get("interaction_type", "")),
                str(data.get("value", "")),
            )
        except KeyError as error:
            raise cherrypy.HTTPError(404, f"Unknown prop: {error.args[0]}") from error
        except ValueError as error:
            raise cherrypy.HTTPError(400, str(error)) from error
        return {"status": "published", "room_id": self.connector.room_id, **data}


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    connector = PropConnector(os.getenv("ROOM_ID", "room1"), catalog)
    connector.start()
    cherrypy.engine.subscribe("stop", connector.stop)
    cherrypy.config.update(server_config(8084))
    cherrypy.quickstart(Root(connector))


if __name__ == "__main__":
    main()
