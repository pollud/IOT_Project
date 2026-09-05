"""Independent safety strategy for falls and unsafe room air conditions."""

from __future__ import annotations

import logging
import os
import threading
import time

from shared.catalog_client import CatalogClient
from shared.config import env_float
from shared.models import AlertEvent, RoomCommand
from shared.mqtt import MQTTClient
from shared.senml import values
from shared.topics import (
    SYSTEM_ALERTS,
    badge_wildcard,
    emergency_command,
    environment_wildcard,
    room_from_topic,
)

LOGGER = logging.getLogger("safety_monitor")


class SafetyMonitor:
    def __init__(self, catalog: CatalogClient) -> None:
        self.catalog = catalog
        self.thresholds = {
            "temperature": env_float("MAX_TEMPERATURE_C", 32.0),
            "humidity": env_float("MAX_HUMIDITY_PERCENT", 75.0),
            "co2": env_float("MAX_CO2_PPM", 1500.0),
            "voc": env_float("MAX_VOC_MG_M3", 2.0),
        }
        self.cooldown = env_float("ALERT_COOLDOWN_SECONDS", 30.0, minimum=0.0)
        self.last_alert: dict[tuple[str, str], float] = {}
        self.lock = threading.Lock()
        self.mqtt = MQTTClient("safety_monitor", heartbeat_payload={"role": "safety_strategy"})
        self.mqtt.on_message_callback = self.on_message

    def start(self) -> None:
        self.catalog.register_service(
            name="safety_monitor",
            description="Fall and environmental safety rules engine",
            mqtt_topics=[badge_wildcard("safety"), environment_wildcard(), SYSTEM_ALERTS, "command/emergency/+"],
        )
        self.mqtt.subscribe(badge_wildcard("safety"), qos=1)
        self.mqtt.subscribe(environment_wildcard(), qos=0)
        self.mqtt.start()

    def stop(self) -> None:
        self.mqtt.stop()

    def _should_alert(self, room_id: str, alert_type: str) -> bool:
        now = time.time()
        key = (room_id, alert_type)
        with self.lock:
            if now - self.last_alert.get(key, 0.0) < self.cooldown:
                return False
            self.last_alert[key] = now
            return True

    def alert(self, room_id: str, alert_type: str, message: str, source: str) -> None:
        if not self._should_alert(room_id, alert_type):
            return
        now = time.time()
        alert = AlertEvent(
            room_id=room_id,
            alert_type=alert_type,
            severity="critical",
            message=message,
            source=source,
            timestamp=now,
        )
        override = RoomCommand(
            room_id=room_id,
            command="emergency_unlock",
            parameters={"reason": alert_type},
            issued_by="safety_monitor",
        )
        self.mqtt.publish(SYSTEM_ALERTS, alert, qos=1)
        self.mqtt.publish(emergency_command(room_id), override, qos=1)
        LOGGER.warning("Safety override for %s: %s", room_id, message)

    def on_message(self, topic: str, payload: str) -> None:
        parts = topic.split("/")
        is_badge_safety = len(parts) == 5 and parts[0] == "game" and parts[2] == "badge" and parts[4] == "safety"
        is_environment = (
            len(parts) == 5 and parts[0] == "room" and parts[2] == "environment" and parts[4] == "telemetry"
        )
        if not (is_badge_safety or is_environment):
            LOGGER.debug("Ignored unrelated MQTT topic: %s", topic)
            return
        room_id = room_from_topic(topic)
        if not room_id:
            LOGGER.warning("Safety message without room correlation: %s", topic)
            return
        try:
            measurements = values(payload)
        except (TypeError, ValueError):
            LOGGER.warning("Ignored malformed SenML safety payload on %s", topic)
            return

        if is_badge_safety and measurements.get("fall_detected") is True:
            badge_id = topic.split("/")[3]
            self.alert(room_id, "fall", f"Fall detected for badge {badge_id}", badge_id)
            return

        if is_environment:
            violations = [
                (name, float(measurements[name]), limit)
                for name, limit in self.thresholds.items()
                if name in measurements and float(measurements[name]) > limit
            ]
            if violations:
                details = ", ".join(f"{name}={value:.1f} (limit {limit:.1f})" for name, value, limit in violations)
                self.alert(room_id, "air_quality", f"Unsafe environment: {details}", topic)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    monitor = SafetyMonitor(catalog)
    monitor.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()


if __name__ == "__main__":
    main()
