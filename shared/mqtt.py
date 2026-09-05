"""Reliable MQTT client wrapper shared by every microservice."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from shared.config import validate_identifier
from shared.constants import DEFAULT_BROKER, DEFAULT_MQTT_PORT
from shared.topics import service_status

LOGGER = logging.getLogger(__name__)


class MQTTClient:
    """MQTT 3.1.1 client with reconnect, retained presence, LWT and heartbeat."""

    def __init__(
        self,
        client_id: str,
        broker: str | None = None,
        port: int | None = None,
        heartbeat_interval: float = 10.0,
        heartbeat_payload: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.client_id = validate_identifier(client_id, "MQTT client_id")
        self.broker = broker or os.getenv("MQTT_BROKER", DEFAULT_BROKER)
        self.port = int(port or os.getenv("MQTT_PORT", str(DEFAULT_MQTT_PORT)))
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_payload = heartbeat_payload
        self.on_message_callback: Callable[[str, str], None] | None = None
        self._subscriptions: list[tuple[str, int]] = []
        self._connected = threading.Event()
        self._running = threading.Event()
        self._stop_requested = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

        self.client = mqtt.Client(client_id=self.client_id, clean_session=True)
        username = os.getenv("MQTT_USERNAME")
        if username:
            self.client.username_pw_set(username, os.getenv("MQTT_PASSWORD"))
        self.client.reconnect_delay_set(min_delay=1, max_delay=15)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        offline = self._presence_payload("offline")
        self.client.will_set(service_status(self.client_id), json.dumps(offline), qos=1, retain=True)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def _presence_payload(self, status: str) -> dict[str, Any]:
        base = self.heartbeat_payload() if callable(self.heartbeat_payload) else self.heartbeat_payload
        payload = dict(base or {})
        payload.update({"service": self.client_id, "status": status, "timestamp": time.time()})
        return payload

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            LOGGER.error("%s MQTT connection rejected with code %s", self.client_id, rc)
            return
        self._connected.set()
        client.publish(
            service_status(self.client_id),
            json.dumps(self._presence_payload("online")),
            qos=1,
            retain=True,
        )
        for topic, qos in self._subscriptions:
            client.subscribe(topic, qos=qos)
        LOGGER.info("%s connected to %s:%s", self.client_id, self.broker, self.port)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected.clear()
        if self._running.is_set() and rc:
            LOGGER.warning("%s disconnected unexpectedly (rc=%s); reconnecting", self.client_id, rc)

    def _on_message(self, client, userdata, message) -> None:
        if not self.on_message_callback:
            return
        try:
            self.on_message_callback(message.topic, message.payload.decode("utf-8"))
        except Exception:
            LOGGER.exception("Unhandled MQTT message in %s on %s", self.client_id, message.topic)

    def start(self, timeout: float = 30.0) -> None:
        if self._running.is_set():
            return
        self._stop_requested.clear()
        self._running.set()
        self.client.connect_async(self.broker, self.port, keepalive=30)
        self.client.loop_start()
        if not self._connected.wait(timeout):
            self.stop()
            raise TimeoutError(f"MQTT broker {self.broker}:{self.port} unavailable after {timeout}s")
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"heartbeat-{self.client_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def stop(self) -> None:
        if not self._running.is_set():
            return
        self._running.clear()
        self._stop_requested.set()
        if self.connected:
            self.publish(service_status(self.client_id), self._presence_payload("offline"), qos=1, retain=True)
        self.client.disconnect()
        self.client.loop_stop()
        self._connected.clear()

    def _heartbeat_loop(self) -> None:
        while self._running.is_set() and not self._stop_requested.is_set():
            if self.connected:
                self.publish(
                    service_status(self.client_id),
                    self._presence_payload("online"),
                    qos=1,
                    retain=True,
                )
            self._stop_requested.wait(self.heartbeat_interval)

    @staticmethod
    def _encode(payload: Any) -> str | bytes:
        if isinstance(payload, bytes):
            return payload
        if isinstance(payload, str):
            return payload
        if dataclasses.is_dataclass(payload):
            payload = dataclasses.asdict(payload)
        return json.dumps(payload, separators=(",", ":"))

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        retain: bool = False,
        wait: bool = False,
        reconnect_timeout: float = 5.0,
    ):
        if not self.connected:
            can_reconnect = self._running.is_set() and not self._stop_requested.is_set()
            if not can_reconnect or not self._connected.wait(reconnect_timeout):
                raise RuntimeError(f"MQTT client {self.client_id} is not connected")
        info = self.client.publish(topic, self._encode(payload), qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed on {topic} with rc={info.rc}")
        if wait:
            info.wait_for_publish(timeout=5)
        return info

    def subscribe(self, topic: str, qos: int = 0) -> None:
        item = (topic, qos)
        if item not in self._subscriptions:
            self._subscriptions.append(item)
        if self.connected:
            result, _ = self.client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT subscribe failed for {topic} with rc={result}")
