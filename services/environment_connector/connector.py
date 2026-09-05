"""Environment Device Connector for BME680-class sensors or a simulator."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any

import cherrypy

from shared.catalog_client import CatalogClient
from shared.config import env_float, validate_identifier
from shared.http import server_config
from shared.mqtt import MQTTClient
from shared.senml import make_pack
from shared.topics import environment

LOGGER = logging.getLogger("environment_connector")


class SimulatedBME680:
    """Bounded random-walk sensor used when Raspberry Pi hardware is absent."""

    def __init__(self, seed: str) -> None:
        # Deterministic sensor simulation; this generator is never used for security.
        self.random = random.Random(seed)  # nosec B311
        self.temperature = 22.0
        self.humidity = 45.0
        self.co2 = 620.0
        self.voc = 0.35

    def read(self) -> dict[str, float]:
        self.temperature = min(30.0, max(16.0, self.temperature + self.random.uniform(-0.15, 0.15)))
        self.humidity = min(75.0, max(25.0, self.humidity + self.random.uniform(-0.5, 0.5)))
        self.co2 = min(1800.0, max(400.0, self.co2 + self.random.uniform(-18.0, 18.0)))
        self.voc = min(3.0, max(0.05, self.voc + self.random.uniform(-0.03, 0.03)))
        return {
            "temperature": self.temperature,
            "humidity": self.humidity,
            "co2": self.co2,
            "voc": self.voc,
        }


class EnvironmentConnector:
    def __init__(self, room_id: str, catalog: CatalogClient) -> None:
        self.room_id = validate_identifier(room_id, "room_id")
        self.catalog = catalog
        room = catalog.room(self.room_id)
        sensor = room["environment_sensor"]
        self.sensor_id = validate_identifier(sensor["sensor_id"], "sensor_id")
        self.calibration = dict(sensor.get("calibration", {}))
        self.interval = env_float("PUBLISH_INTERVAL", 10.0, minimum=0.2)
        self.provider = SimulatedBME680(f"{self.room_id}:{self.sensor_id}")
        self.last_sample: dict[str, Any] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.mqtt = MQTTClient(
            f"environment_connector_{self.room_id}",
            heartbeat_payload=lambda: {"room_id": self.room_id, "sensor_id": self.sensor_id},
        )

    def start(self) -> None:
        self.catalog.register_service(
            name=f"environment_connector_{self.room_id}",
            description="BME680 environment device connector",
            endpoint=os.getenv("SERVICE_URL", f"http://environment_connector_{self.room_id}:8081"),
            room_id=self.room_id,
            mqtt_topics=[environment(self.room_id, self.sensor_id)],
        )
        self.catalog.register_device(
            device_id=f"env_{self.room_id}",
            kind="environment_sensor",
            room_id=self.room_id,
            connector=f"environment_connector_{self.room_id}",
            metadata={"sensor_id": self.sensor_id, "measurements": ["temperature", "humidity", "co2", "voc"]},
        )
        self.mqtt.start()
        self._thread = threading.Thread(target=self._publish_loop, name=f"environment-{self.room_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.mqtt.stop()

    def sample(self) -> list[dict[str, Any]]:
        raw = self.provider.read()
        calibrated = {
            "temperature": raw["temperature"] + float(self.calibration.get("temperature_offset", 0.0)),
            "humidity": raw["humidity"] + float(self.calibration.get("humidity_offset", 0.0)),
            "co2": raw["co2"] + float(self.calibration.get("co2_offset", 0.0)),
            "voc": raw["voc"] + float(self.calibration.get("voc_offset", 0.0)),
        }
        self.last_sample = {**calibrated, "timestamp": time.time()}
        return make_pack(
            f"urn:escape-room:{self.room_id}:environment:{self.sensor_id}:",
            [
                ("temperature", round(calibrated["temperature"], 2), "Cel"),
                ("humidity", round(calibrated["humidity"], 2), "%RH"),
                ("co2", round(calibrated["co2"], 1), "ppm"),
                ("voc", round(calibrated["voc"], 3), "mg/m3"),
            ],
            timestamp=self.last_sample["timestamp"],
        )

    def _publish_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.mqtt.publish(environment(self.room_id, self.sensor_id), self.sample(), qos=0)
            except RuntimeError:
                LOGGER.warning("Environment telemetry paused while MQTT is disconnected")
            except Exception:
                LOGGER.exception("Environment publication failed")
            self._stop.wait(self.interval)


class Root:
    def __init__(self, connector: EnvironmentConnector) -> None:
        self.connector = connector

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok" if self.connector.mqtt.connected else "degraded",
            "room_id": self.connector.room_id,
            "sensor_id": self.connector.sensor_id,
            "last_sample": self.connector.last_sample,
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def calibration(self):
        if cherrypy.request.method.upper() != "GET":
            raise cherrypy.HTTPError(405, "GET required")
        return {"room_id": self.connector.room_id, "sensor_id": self.connector.sensor_id, "calibration": self.connector.calibration}


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    connector = EnvironmentConnector(os.getenv("ROOM_ID", "room1"), catalog)
    connector.start()
    cherrypy.engine.subscribe("stop", connector.stop)
    cherrypy.config.update(server_config(8081))
    cherrypy.quickstart(Root(connector))


if __name__ == "__main__":
    main()
