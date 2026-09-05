"""Game Catalog: CRUD registry, room discovery and strategy distribution."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import cherrypy
import jsonschema

from shared.config import load_config, validate_identifier
from shared.fsm_schema import validate_strategy
from shared.http import server_config
from shared.models import ConfigUpdateEvent
from shared.mqtt import MQTTClient
from shared.topics import SERVICE_STATUS_WILDCARD, catalog_update

LOGGER = logging.getLogger("catalog")


def read_json_body() -> dict[str, Any]:
    content_type = cherrypy.request.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        raise cherrypy.HTTPError(415, "Content-Type must be application/json")
    try:
        data = json.loads(cherrypy.request.body.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise cherrypy.HTTPError(400, f"Invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise cherrypy.HTTPError(400, "JSON body must be an object")
    return data


class CatalogStore:
    """Thread-safe persistent state owned exclusively by the Catalog service."""

    def __init__(self, config_dir: str | Path) -> None:
        self.config_dir = Path(config_dir)
        self.catalog_path = self.config_dir / "catalog.json"
        self.rooms_path = self.config_dir / "rooms.json"
        self.lock = threading.RLock()
        catalog = load_config(self.catalog_path)
        rooms = load_config(self.rooms_path)
        self.services: list[dict[str, Any]] = catalog.get("registered_services", [])
        self.devices: list[dict[str, Any]] = catalog.get("registered_devices", [])
        self.rooms: list[dict[str, Any]] = rooms.get("rooms", [])
        for room in self.rooms:
            self._validate_room(room)
        room_ids = [room["room_id"] for room in self.rooms]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError("Room IDs must be globally unique")
        all_resources: list[str] = []
        for room in self.rooms:
            all_resources.extend(self._defined_device_ids(room))
            strategy_path = self.config_dir / f"strategy_{room['room_id']}.json"
            if not strategy_path.is_file():
                raise ValueError(f"Missing strategy for {room['room_id']}")
            self.validate_room_strategy(load_config(strategy_path), room["room_id"], require_current_version=True)
        if len(all_resources) != len(set(all_resources)):
            raise ValueError("Badge, prop and registered connector device IDs must be globally unique")
        for service in self.services:
            self._validate_service(service)
        for device in self.devices:
            self._validate_device(device)

    @staticmethod
    def _atomic_json_write(path: Path, data: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def _save_catalog(self) -> None:
        self._atomic_json_write(
            self.catalog_path,
            {"registered_services": self.services, "registered_devices": self.devices},
        )

    def _save_rooms(self) -> None:
        self._atomic_json_write(self.rooms_path, {"rooms": self.rooms})

    def _validate_service(self, record: dict[str, Any]) -> None:
        if record.get("type") != "service":
            raise ValueError("Service record needs type='service'")
        validate_identifier(str(record.get("name", "")), "service name")
        if not record.get("description"):
            raise ValueError("Service record needs a description")
        if record.get("room_id"):
            room_id = validate_identifier(str(record["room_id"]), "room_id")
            if not any(room["room_id"] == room_id for room in self.rooms):
                raise ValueError(f"Unknown room_id: {room_id}")

    def _validate_device(self, record: dict[str, Any]) -> None:
        if record.get("type") != "device":
            raise ValueError("Device record needs type='device'")
        validate_identifier(str(record.get("device_id", "")), "device_id")
        room_id = validate_identifier(str(record.get("room_id", "")), "room_id")
        if not any(room["room_id"] == room_id for room in self.rooms):
            raise ValueError(f"Unknown room_id: {room_id}")
        if not record.get("kind") or not record.get("connector"):
            raise ValueError("Device record needs kind and connector")
        connector = self._find(self.services, "name", str(record["connector"]))
        if not connector:
            raise ValueError(f"Unknown connector service: {record['connector']}")
        if connector.get("room_id") and connector["room_id"] != room_id:
            raise ValueError("Device room_id does not match its connector service")

    @staticmethod
    def _validate_room(record: dict[str, Any]) -> None:
        room_id = validate_identifier(str(record.get("room_id", "")), "room_id")
        required = {
            "name",
            "theme",
            "strategy_version",
            "max_duration_seconds",
            "dimensions",
            "environment_sensor",
            "badges",
            "props",
            "actuators",
        }
        missing = required - record.keys()
        if missing:
            raise ValueError(f"Room record misses {sorted(missing)}")
        if not str(record["name"]).strip() or not str(record["theme"]).strip():
            raise ValueError("Room name and theme cannot be empty")
        if not str(record["strategy_version"]).strip():
            raise ValueError("Room strategy_version cannot be empty")
        try:
            if float(record["max_duration_seconds"]) <= 0:
                raise ValueError
            dimensions = record["dimensions"]
            if not isinstance(dimensions, dict) or float(dimensions["width_m"]) <= 0 or float(dimensions["height_m"]) <= 0:
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Room duration and dimensions must be positive numbers") from error
        environment_sensor = record["environment_sensor"]
        if not isinstance(environment_sensor, dict):
            raise ValueError("environment_sensor must be an object")
        validate_identifier(str(environment_sensor.get("sensor_id", "")), "sensor_id")
        if not isinstance(record["badges"], list) or not record["badges"]:
            raise ValueError(f"Room {room_id} needs at least one badge")
        if not isinstance(record["props"], list) or not record["props"]:
            raise ValueError(f"Room {room_id} needs at least one prop")
        identifiers: list[str] = []
        for badge_definition in record["badges"]:
            if not isinstance(badge_definition, dict):
                raise ValueError("Every badge definition must be an object")
            identifiers.append(validate_identifier(str(badge_definition.get("badge_id", "")), "badge_id"))
        for prop_definition in record["props"]:
            if not isinstance(prop_definition, dict):
                raise ValueError("Every prop definition must be an object")
            identifiers.append(validate_identifier(str(prop_definition.get("prop_id", "")), "prop_id"))
            if not prop_definition.get("sensor") or "expected_value" not in prop_definition:
                raise ValueError("Every prop needs sensor and expected_value")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Room {room_id} has duplicate badge/prop IDs")
        actuators = record["actuators"]
        if (
            not isinstance(actuators, list)
            or not all(isinstance(item, str) for item in actuators)
            or not {"main_door", "lights", "audio"}.issubset(actuators)
        ):
            raise ValueError("Room actuators must include main_door, lights and audio")

    @staticmethod
    def _defined_device_ids(room: dict[str, Any]) -> set[str]:
        room_id = room["room_id"]
        return {
            *(badge["badge_id"] for badge in room["badges"]),
            *(prop["prop_id"] for prop in room["props"]),
            f"env_{room_id}",
            f"actuator_{room_id}",
        }

    def validate_room_strategy(
        self,
        strategy: dict[str, Any],
        room_id: str,
        require_current_version: bool = False,
    ) -> None:
        validate_strategy(strategy)
        room = self.room(room_id)
        if not room or strategy["room_id"] != room_id:
            raise ValueError("Strategy room_id does not match a configured room")
        if require_current_version and strategy["version"] != room["strategy_version"]:
            raise ValueError(f"Strategy version mismatch for {room_id}")
        configured_props = {prop["prop_id"] for prop in room["props"]}
        referenced_props = {
            transition["prop_id"]
            for state in strategy["states"].values()
            for transition in state["transitions"]
            if transition["trigger"] == "event"
        }
        unknown = referenced_props - configured_props
        if unknown:
            raise ValueError(f"Strategy references unconfigured props: {sorted(unknown)}")

    @staticmethod
    def _find(records: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
        return next((deepcopy(record) for record in records if record.get(key) == value), None)

    def list_services(self) -> list[dict[str, Any]]:
        with self.lock:
            return deepcopy(self.services)

    def service(self, name: str) -> dict[str, Any] | None:
        with self.lock:
            return self._find(self.services, "name", name)

    def put_service(self, record: dict[str, Any], create_only: bool = False) -> dict[str, Any]:
        with self.lock:
            self._validate_service(record)
            name = record["name"]
            existing = self._find(self.services, "name", name)
            if create_only and existing:
                raise KeyError(name)
            if existing and existing.get("room_id") != record.get("room_id"):
                if any(device.get("connector") == name for device in self.devices):
                    raise ValueError("Cannot move a connector service while devices reference it")
            stored = deepcopy(record)
            stored.setdefault("created_at", existing.get("created_at") if existing else time.time())
            stored["last_seen"] = time.time()
            stored["online_status"] = "online"
            if existing:
                self.services = [stored if item.get("name") == name else item for item in self.services]
            else:
                self.services.append(stored)
            self._save_catalog()
            return deepcopy(stored)

    def delete_service(self, name: str) -> bool:
        with self.lock:
            if any(device.get("connector") == name for device in self.devices):
                raise ValueError("Delete correlated devices before deleting their connector service")
            before = len(self.services)
            self.services = [item for item in self.services if item.get("name") != name]
            if len(self.services) == before:
                return False
            self._save_catalog()
            return True

    def list_devices(self) -> list[dict[str, Any]]:
        with self.lock:
            return deepcopy(self.devices)

    def device(self, device_id: str) -> dict[str, Any] | None:
        with self.lock:
            return self._find(self.devices, "device_id", device_id)

    def put_device(self, record: dict[str, Any], create_only: bool = False) -> dict[str, Any]:
        with self.lock:
            self._validate_device(record)
            device_id = record["device_id"]
            existing = self._find(self.devices, "device_id", device_id)
            if create_only and existing:
                raise KeyError(device_id)
            if existing and existing.get("room_id") != record.get("room_id"):
                raise ValueError("Cannot move an existing device to another room")
            stored = deepcopy(record)
            stored.setdefault("created_at", existing.get("created_at") if existing else time.time())
            stored["last_seen"] = time.time()
            stored["online_status"] = "online"
            if existing:
                self.devices = [stored if item.get("device_id") == device_id else item for item in self.devices]
            else:
                self.devices.append(stored)
            self._save_catalog()
            return deepcopy(stored)

    def delete_device(self, device_id: str) -> bool:
        with self.lock:
            before = len(self.devices)
            self.devices = [item for item in self.devices if item.get("device_id") != device_id]
            if len(self.devices) == before:
                return False
            self._save_catalog()
            return True

    def list_rooms(self) -> list[dict[str, Any]]:
        with self.lock:
            return deepcopy(self.rooms)

    def room(self, room_id: str) -> dict[str, Any] | None:
        with self.lock:
            return self._find(self.rooms, "room_id", room_id)

    def put_room(self, record: dict[str, Any], create_only: bool = False) -> dict[str, Any]:
        self._validate_room(record)
        room_id = record["room_id"]
        with self.lock:
            existing = self._find(self.rooms, "room_id", room_id)
            if create_only and existing:
                raise KeyError(room_id)
            incoming_ids = self._defined_device_ids(record)
            other_ids = {
                device_id
                for room in self.rooms
                if room["room_id"] != room_id
                for device_id in self._defined_device_ids(room)
            }
            duplicates = incoming_ids & other_ids
            if duplicates:
                raise ValueError(f"Room resource IDs already exist: {sorted(duplicates)}")
            removed_ids = self._defined_device_ids(existing) - incoming_ids if existing else set()
            if any(device.get("device_id") in removed_ids for device in self.devices):
                raise ValueError("Delete removed room devices before updating the room")
            if existing:
                self.rooms = [deepcopy(record) if item.get("room_id") == room_id else item for item in self.rooms]
            else:
                self.rooms.append(deepcopy(record))
            self._save_rooms()
            return deepcopy(record)

    def delete_room(self, room_id: str) -> bool:
        with self.lock:
            if any(device.get("room_id") == room_id for device in self.devices):
                raise ValueError("Delete correlated devices before deleting the room")
            if any(service.get("room_id") == room_id for service in self.services):
                raise ValueError("Delete correlated services before deleting the room")
            before = len(self.rooms)
            self.rooms = [item for item in self.rooms if item.get("room_id") != room_id]
            if len(self.rooms) == before:
                return False
            self._save_rooms()
            return True

    def update_presence(self, actor: str, status: str, timestamp: float) -> None:
        with self.lock:
            for record in [*self.services, *self.devices]:
                if record.get("name") == actor or record.get("device_id") == actor:
                    record["last_seen"] = timestamp
                    record["online_status"] = status


class CatalogService:
    def __init__(self, store: CatalogStore) -> None:
        self.store = store
        self.mqtt = MQTTClient("catalog", heartbeat_payload={"role": "registry"})
        self.mqtt.on_message_callback = self.on_presence

    def start(self) -> None:
        self.mqtt.subscribe(SERVICE_STATUS_WILDCARD, qos=1)
        self.mqtt.start()

    def on_presence(self, topic: str, payload: str) -> None:
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise TypeError("Presence payload must be a JSON object")
            actor = str(data.get("service") or topic.split("/", 1)[1])
            self.store.update_presence(
                actor,
                str(data.get("status", "unknown")),
                float(data.get("timestamp", time.time())),
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            LOGGER.warning("Ignored malformed presence message on %s", topic)

    def publish_strategy_update(self, strategy: dict[str, Any]) -> None:
        event = ConfigUpdateEvent(
            room_id=strategy["room_id"],
            version=strategy["version"],
            timestamp=time.time(),
        )
        self.mqtt.publish(catalog_update(strategy["room_id"]), event, qos=1, retain=True)


class EntityRoute:
    def __init__(self, store: CatalogStore, entity: str) -> None:
        self.store = store
        self.entity = entity

    def handle(self, **params):
        method = cherrypy.request.method.upper()
        key_name = {"services": "name", "devices": "device_id", "rooms": "room_id"}[self.entity]
        key = params.get(key_name)
        list_method = getattr(self.store, f"list_{self.entity}")
        get_method = getattr(self.store, self.entity[:-1])
        put_method = getattr(self.store, f"put_{self.entity[:-1]}")
        delete_method = getattr(self.store, f"delete_{self.entity[:-1]}")

        if method == "GET":
            if key:
                record = get_method(key)
                if not record:
                    raise cherrypy.HTTPError(404, f"Unknown {key_name}: {key}")
                return {self.entity[:-1]: record}
            return {self.entity: list_method()}

        if method in {"POST", "PUT"}:
            record = read_json_body()
            if key and key != record.get(key_name):
                raise cherrypy.HTTPError(400, f"URL and body {key_name} do not match")
            try:
                stored = put_method(record, create_only=(method == "POST"))
            except KeyError as error:
                raise cherrypy.HTTPError(409, f"Already exists: {error.args[0]}") from error
            except ValueError as error:
                raise cherrypy.HTTPError(400, str(error)) from error
            cherrypy.response.status = 201 if method == "POST" else 200
            return {self.entity[:-1]: stored}

        if method == "DELETE":
            if not key:
                raise cherrypy.HTTPError(400, f"Query parameter {key_name} is required")
            try:
                deleted = delete_method(key)
            except ValueError as error:
                raise cherrypy.HTTPError(409, str(error)) from error
            if not deleted:
                raise cherrypy.HTTPError(404, f"Unknown {key_name}: {key}")
            return {"deleted": key}

        raise cherrypy.HTTPError(405, "Allowed methods: GET, POST, PUT, DELETE")


class ConfigRoute:
    def __init__(self, service: CatalogService, config_dir: Path) -> None:
        self.service = service
        self.config_dir = config_dir

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def default(self, room_id: str):
        try:
            validate_identifier(room_id, "room_id")
        except ValueError as error:
            raise cherrypy.HTTPError(400, str(error)) from error
        if not self.service.store.room(room_id):
            raise cherrypy.HTTPError(404, f"Unknown room: {room_id}")
        path = self.config_dir / f"strategy_{room_id}.json"
        method = cherrypy.request.method.upper()
        if method == "GET":
            if not path.exists():
                raise cherrypy.HTTPError(404, "Strategy not configured")
            return load_config(path)
        if method == "PUT":
            strategy = read_json_body()
            try:
                self.service.store.validate_room_strategy(strategy, room_id)
            except (ValueError, jsonschema.ValidationError) as error:
                raise cherrypy.HTTPError(400, str(error)) from error
            if strategy["room_id"] != room_id:
                raise cherrypy.HTTPError(400, "Strategy room_id does not match URL")
            CatalogStore._atomic_json_write(path, strategy)
            room = self.service.store.room(room_id)
            room["strategy_version"] = strategy["version"]
            self.service.store.put_room(room)
            self.service.publish_strategy_update(strategy)
            return {"updated": room_id, "version": strategy["version"]}
        raise cherrypy.HTTPError(405, "Allowed methods: GET, PUT")


class Root:
    def __init__(self, service: CatalogService, config_dir: Path) -> None:
        self.service = service
        self._entity_routes = {
            "services": EntityRoute(service.store, "services"),
            "devices": EntityRoute(service.store, "devices"),
            "rooms": EntityRoute(service.store, "rooms"),
        }
        self.config = ConfigRoute(service, config_dir)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def services(self, **params):
        return self._entity_routes["services"].handle(**params)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def devices(self, **params):
        return self._entity_routes["devices"].handle(**params)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def rooms(self, **params):
        return self._entity_routes["rooms"].handle(**params)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok",
            "timestamp": time.time(),
            "services": len(self.service.store.list_services()),
            "devices": len(self.service.store.list_devices()),
            "rooms": len(self.service.store.list_rooms()),
            "mqtt_connected": self.service.mqtt.connected,
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def register(self):
        if cherrypy.request.method.upper() != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        record = read_json_body()
        try:
            if record.get("type") == "service":
                stored = self.service.store.put_service(record)
            elif record.get("type") == "device":
                stored = self.service.store.put_device(record)
            else:
                raise ValueError("type must be 'service' or 'device'")
        except ValueError as error:
            raise cherrypy.HTTPError(400, str(error)) from error
        return {"status": "registered", "record": stored}


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    config_dir = Path(os.getenv("CONFIG_DIR", "/app/config"))
    if not config_dir.exists():
        config_dir = Path("config")
    store = CatalogStore(config_dir)
    service = CatalogService(store)
    service.start()
    cherrypy.engine.subscribe("stop", service.mqtt.stop)
    cherrypy.config.update(server_config(8080))
    cherrypy.quickstart(Root(service, config_dir))


if __name__ == "__main__":
    main()
