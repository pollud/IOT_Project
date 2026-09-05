"""Room Control MQTT adapter hosting one recoverable FSM instance."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from services.room_control.fsm import RoomFSM
from services.room_control.loader import load_strategy_from_catalog
from shared.catalog_client import CatalogClient
from shared.config import validate_identifier
from shared.mqtt import MQTTClient
from shared.senml import values
from shared.topics import catalog_update, game_status, prop_wildcard, room_command

LOGGER = logging.getLogger("room_control")


class RoomController:
    def __init__(self, room_id: str, catalog: CatalogClient) -> None:
        self.room_id = validate_identifier(room_id, "room_id")
        self.catalog = catalog
        self.fsm: RoomFSM | None = None
        self._recovered_status: dict[str, Any] | None = None
        self._recovery_received = threading.Event()
        self.mqtt = MQTTClient(
            f"room_control_{self.room_id}",
            heartbeat_payload=lambda: {
                "room_id": self.room_id,
                "state": self.fsm.current_state if self.fsm else "initializing",
            },
        )
        self.mqtt.on_message_callback = self.on_message

    def start(self) -> None:
        strategy = load_strategy_from_catalog(self.catalog, self.room_id)
        service_name = f"room_control_{self.room_id}"
        self.catalog.register_service(
            name=service_name,
            description="Recoverable room game-flow finite state machine",
            room_id=self.room_id,
            mqtt_topics=[
                prop_wildcard(self.room_id, "interaction"),
                room_command(self.room_id),
                game_status(self.room_id),
                catalog_update(self.room_id),
            ],
        )
        self.mqtt.subscribe(prop_wildcard(self.room_id, "interaction"), qos=1)
        self.mqtt.subscribe(room_command(self.room_id), qos=1)
        self.mqtt.subscribe(game_status(self.room_id), qos=1)
        self.mqtt.subscribe(catalog_update(self.room_id), qos=1)
        self.mqtt.start()
        self._recovery_received.wait(float(os.getenv("RECOVERY_WINDOW_SECONDS", "0.75")))
        self.fsm = RoomFSM(self.room_id, strategy, self.mqtt, self._recovered_status)
        self.fsm.start()

    def stop(self) -> None:
        if self.fsm:
            self.fsm.close()
        self.mqtt.stop()

    def on_message(self, topic: str, payload: str) -> None:
        if topic == game_status(self.room_id):
            if self.fsm is None:
                try:
                    status = json.loads(payload)
                    if status.get("room_id") == self.room_id:
                        self._recovered_status = status
                        self._recovery_received.set()
                except json.JSONDecodeError:
                    LOGGER.warning("Ignored malformed retained room status")
            return

        if topic == catalog_update(self.room_id):
            if self.fsm is not None:
                try:
                    self.fsm.load_strategy(load_strategy_from_catalog(self.catalog, self.room_id))
                    LOGGER.info("[%s] strategy hot-reloaded", self.room_id)
                except Exception:
                    LOGGER.exception("[%s] rejected strategy update", self.room_id)
            return

        if self.fsm is None:
            return

        if topic == room_command(self.room_id):
            try:
                command = json.loads(payload)
            except json.JSONDecodeError:
                LOGGER.warning("Ignored malformed room command")
                return
            if not isinstance(command, dict):
                LOGGER.warning("Ignored non-object room command")
                return
            if command.get("room_id") != self.room_id:
                return
            name = command.get("command")
            if name in {"reset", "start"}:
                self.fsm.reset_room()
            return

        if topic.endswith("/interaction"):
            try:
                measurement = values(payload)
                prop_id = topic.split("/")[3]
                transitioned = self.fsm.event_transition(
                    prop_id,
                    str(measurement["interaction_type"]),
                    str(measurement["value"]),
                )
                if not transitioned:
                    LOGGER.info("[%s] interaction did not match current state: %s", self.room_id, prop_id)
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Ignored malformed prop interaction on %s", topic)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    controller = RoomController(os.getenv("ROOM_ID", "room1"), catalog)
    controller.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()


if __name__ == "__main__":
    main()
