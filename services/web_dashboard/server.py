"""Unified Game Master dashboard backend, MQTT bridge and SSE gateway."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import cherrypy
import requests
from cherrypy.lib.static import serve_file

from shared.catalog_client import CatalogClient
from shared.constants import DEFAULT_ANALYTICS_URL
from shared.http import server_config
from shared.models import RoomCommand
from shared.mqtt import MQTTClient
from shared.senml import make_pack
from shared.senml import values as senml_values
from shared.topics import (
    SERVICE_STATUS_WILDCARD,
    SYSTEM_ALERTS,
    event_type_from_topic,
    prop,
    room_command,
    room_from_topic,
)

LOGGER = logging.getLogger("web_dashboard")


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


class DashboardBridge:
    """Maintains a live cache and fans MQTT events out to SSE clients."""

    def __init__(self, catalog: CatalogClient) -> None:
        self.catalog = catalog
        rooms = catalog.rooms()
        self.room_definitions = {room["room_id"]: room for room in rooms}
        self.rooms: dict[str, dict[str, Any]] = {
            room_id: {
                "definition": room,
                "status": None,
                "environment": None,
                "badges": {},
                "props": {},
                "last_transition": None,
            }
            for room_id, room in self.room_definitions.items()
        }
        self.presence: dict[str, dict[str, Any]] = {}
        self.alerts: deque[dict[str, Any]] = deque(maxlen=50)
        self.lock = threading.RLock()
        self.listeners: set[queue.Queue[dict[str, Any]]] = set()
        self.mqtt = MQTTClient(
            "web_dashboard",
            heartbeat_payload=lambda: {"sse_clients": len(self.listeners), "rooms": len(self.rooms)},
        )
        self.mqtt.on_message_callback = self.on_message

    @staticmethod
    def subscriptions() -> list[tuple[str, int]]:
        return [
            ("room/+/environment/+/telemetry", 0),
            ("game/+/badge/+/+", 0),
            ("game/+/prop/+/+", 0),
            ("game/+/status", 1),
            ("game/+/transition", 1),
            ("session/+/+", 1),
            (SYSTEM_ALERTS, 1),
            (SERVICE_STATUS_WILDCARD, 1),
            ("analytics/+/summary", 1),
        ]

    def start(self) -> None:
        self.catalog.register_service(
            name="web_dashboard",
            description="Robust Game Master GUI replacing Node-RED, Telegram and ThingSpeak",
            endpoint=os.getenv("SERVICE_URL", "http://web_dashboard:8087"),
            mqtt_topics=[topic for topic, _ in self.subscriptions()],
        )
        for topic, qos in self.subscriptions():
            self.mqtt.subscribe(topic, qos=qos)
        self.mqtt.start()

    def stop(self) -> None:
        self.mqtt.stop()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "rooms": json.loads(json.dumps(self.rooms)),
                "presence": json.loads(json.dumps(self.presence)),
                "alerts": list(self.alerts),
            }

    def _decode(self, parsed: Any) -> dict[str, Any] | list[Any]:
        if isinstance(parsed, list):
            return senml_values(parsed)
        return parsed

    def on_message(self, topic: str, payload: str) -> None:
        try:
            parsed = json.loads(payload)
            decoded = self._decode(parsed)
        except (ValueError, TypeError, json.JSONDecodeError):
            LOGGER.warning("Dashboard ignored malformed payload on %s", topic)
            return
        room_id = room_from_topic(topic)
        event_type = event_type_from_topic(topic)
        now = time.time()
        with self.lock:
            if topic.startswith("status/") and isinstance(decoded, dict):
                actor = topic.split("/", 1)[1]
                self.presence[actor] = decoded
            elif topic == SYSTEM_ALERTS and isinstance(decoded, dict):
                room_id = decoded.get("room_id")
                self.alerts.appendleft(decoded)
            elif room_id in self.rooms:
                room = self.rooms[room_id]
                parts = topic.split("/")
                if event_type == "environment":
                    room["environment"] = {**decoded, "timestamp": now}
                elif event_type.startswith("badge_") and len(parts) >= 5:
                    badge_id = parts[3]
                    room["badges"].setdefault(badge_id, {}).update(decoded)
                    room["badges"][badge_id]["timestamp"] = now
                elif event_type.startswith("prop_") and len(parts) >= 5:
                    prop_id = parts[3]
                    room["props"].setdefault(prop_id, {}).update(decoded)
                    room["props"][prop_id]["timestamp"] = now
                elif event_type == "game_status" and isinstance(decoded, dict):
                    room["status"] = decoded
                elif event_type == "game_transition" and isinstance(decoded, dict):
                    room["last_transition"] = decoded
        self.broadcast(
            {
                "topic": topic,
                "room_id": room_id,
                "event_type": event_type,
                "payload": parsed,
                "decoded": decoded,
                "received_at": now,
            }
        )

    def add_listener(self) -> queue.Queue[dict[str, Any]]:
        listener: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=500)
        with self.lock:
            self.listeners.add(listener)
        return listener

    def remove_listener(self, listener: queue.Queue[dict[str, Any]]) -> None:
        with self.lock:
            self.listeners.discard(listener)

    def broadcast(self, event: dict[str, Any]) -> None:
        with self.lock:
            listeners = list(self.listeners)
        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:
                try:
                    listener.get_nowait()
                    listener.put_nowait(event)
                except (queue.Empty, queue.Full):
                    LOGGER.warning("Dropped SSE event for a slow client")


class StatsProxy:
    exposed = True

    def __init__(self, analytics_url: str) -> None:
        self.analytics_url = analytics_url.rstrip("/")
        self.session = requests.Session()
        self.allowed = {"room", "prop", "environment", "history", "heatmap", "bottlenecks", "safety", "maintenance", "game_center", "reset"}

    @cherrypy.expose
    def default(self, *path, **params):
        if not path or path[0] not in self.allowed:
            raise cherrypy.HTTPError(404)
        method = cherrypy.request.method.upper()
        if method not in {"GET", "POST"}:
            raise cherrypy.HTTPError(405, "GET or POST required")
        if path[0] == "reset" and method != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        url = f"{self.analytics_url}/stats/{'/'.join(path)}"
        try:
            response = self.session.request(method, url, params=params, timeout=8.0)
        except requests.RequestException as error:
            raise cherrypy.HTTPError(502, f"Analytics unavailable: {error}") from error
        cherrypy.response.status = response.status_code
        cherrypy.response.headers["Content-Type"] = response.headers.get("Content-Type", "application/json")
        return response.content


class StrategyProxy:
    exposed = True

    def __init__(self, catalog: CatalogClient) -> None:
        self.catalog = catalog

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def default(self, room_id: str):
        if cherrypy.request.method.upper() != "GET":
            raise cherrypy.HTTPError(405, "GET required")
        try:
            return self.catalog.strategy(room_id)
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else 502
            raise cherrypy.HTTPError(status, "Strategy unavailable") from error


class API:
    def __init__(self, bridge: DashboardBridge, catalog: CatalogClient) -> None:
        self.bridge = bridge
        self.catalog = catalog
        self.stats = StatsProxy(os.getenv("ANALYTICS_URL", DEFAULT_ANALYTICS_URL))
        self.strategy = StrategyProxy(catalog)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok" if self.bridge.mqtt.connected else "degraded",
            "mqtt_connected": self.bridge.mqtt.connected,
            "sse_clients": len(self.bridge.listeners),
            "rooms": len(self.bridge.rooms),
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def rooms(self):
        return {"rooms": list(self.bridge.room_definitions.values())}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def status(self):
        return self.bridge.snapshot()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def presence(self):
        return {"presence": self.bridge.snapshot()["presence"]}

    @cherrypy.expose
    def stream(self):
        cherrypy.response.headers.update(
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
        cherrypy.response.stream = True
        listener = self.bridge.add_listener()
        snapshot = self.bridge.snapshot()

        def generate():
            try:
                yield f"event: snapshot\ndata: {json.dumps(snapshot, separators=(',', ':'))}\n\n".encode()
                while True:
                    try:
                        event = listener.get(timeout=15.0)
                        yield f"event: mqtt\ndata: {json.dumps(event, separators=(',', ':'))}\n\n".encode()
                    except queue.Empty:
                        yield b": keep-alive\n\n"
            except GeneratorExit:
                return
            finally:
                self.bridge.remove_listener(listener)

        return generate()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def command(self):
        if cherrypy.request.method.upper() != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        data = read_json_body()
        room_id = str(data.get("room_id", ""))
        if room_id not in self.bridge.room_definitions:
            raise cherrypy.HTTPError(404, f"Unknown room: {room_id}")
        name = str(data.get("command", ""))
        definition = self.bridge.room_definitions[room_id]

        if name == "trigger_prop":
            prop_id = str(data.get("prop_id", ""))
            configured = next((item for item in definition["props"] if item["prop_id"] == prop_id), None)
            if not configured:
                raise cherrypy.HTTPError(404, f"Unknown prop: {prop_id}")
            interaction_type = str(data.get("interaction_type", ""))
            if interaction_type != configured["sensor"]:
                raise cherrypy.HTTPError(400, f"Prop {prop_id} expects {configured['sensor']}")
            value = str(data.get("value", ""))
            expected_value = configured.get("expected_value")
            if expected_value is not None and value != str(expected_value):
                raise cherrypy.HTTPError(400, f"Prop {prop_id} expects value={expected_value}")
            topic = prop(room_id, prop_id, "interaction")
            payload: Any = make_pack(
                f"urn:escape-room:{room_id}:prop:{prop_id}:",
                [("interaction_type", interaction_type, None), ("value", value, None)],
            )
        else:
            aliases = {"unlockDoor": "unlock", "lockDoor": "lock", "playAudio": "play_audio", "setLights": "set_lights"}
            name = aliases.get(name, name)
            allowed = {"reset", "start", "unlock", "lock", "play_audio", "set_lights"}
            if name not in allowed:
                raise cherrypy.HTTPError(400, f"Unsupported command: {name}")
            raw_parameters = data.get("parameters") or {}
            if not isinstance(raw_parameters, dict):
                raise cherrypy.HTTPError(400, "parameters must be a JSON object")
            parameters = dict(raw_parameters)
            if name == "play_audio" and "track" in data:
                parameters["track"] = data["track"]
            if name == "set_lights" and "color" in data:
                parameters["color"] = data["color"]
            if name == "play_audio" and not str(parameters.get("track", "")).strip():
                raise cherrypy.HTTPError(400, "play_audio requires a non-empty track")
            if name == "set_lights" and not str(parameters.get("color", "")).strip():
                raise cherrypy.HTTPError(400, "set_lights requires a non-empty color")
            topic = room_command(room_id)
            payload = RoomCommand(
                room_id=room_id,
                command=name,
                parameters=parameters,
                issued_by="game_master_dashboard",
            )
        self.bridge.mqtt.publish(topic, payload, qos=1, wait=True)
        return {"accepted": True, "topic": topic, "room_id": room_id, "command": name}


class Root:
    def __init__(self, api: API, dist_dir: Path) -> None:
        self.api = api
        self.dist_dir = dist_dir.resolve()

    @cherrypy.expose
    def index(self):
        return serve_file(str(self.dist_dir / "index.html"), content_type="text/html")

    @cherrypy.expose
    def default(self, *path):
        candidate = (self.dist_dir / Path(*path)).resolve()
        if self.dist_dir not in candidate.parents:
            raise cherrypy.HTTPError(404)
        if candidate.is_file():
            content_type, _ = mimetypes.guess_type(candidate)
            return serve_file(str(candidate), content_type=content_type)
        return self.index()


def security_headers() -> None:
    cherrypy.response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'",
        }
    )


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    bridge = DashboardBridge(catalog)
    bridge.start()
    cherrypy.engine.subscribe("stop", bridge.stop)
    cherrypy.tools.security_headers = cherrypy.Tool("before_finalize", security_headers)
    settings = server_config(8087)
    settings["tools.security_headers.on"] = True
    cherrypy.config.update(settings)
    dist_dir = Path(os.getenv("DASHBOARD_DIST", "/app/dist"))
    if not dist_dir.exists():
        dist_dir = Path("services/web_dashboard/dist")
    cherrypy.quickstart(Root(API(bridge, catalog), dist_dir))


if __name__ == "__main__":
    main()
