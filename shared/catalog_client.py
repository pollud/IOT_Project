"""REST client used by actors to discover configuration and self-register."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from shared.constants import DEFAULT_CATALOG_URL


class CatalogClient:
    def __init__(self, base_url: str | None = None, timeout: float = 3.0) -> None:
        self.base_url = (base_url or os.getenv("CATALOG_URL", DEFAULT_CATALOG_URL)).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else None

    def wait_until_ready(self, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._request("GET", "/health")
                return
            except (requests.RequestException, ValueError) as error:
                last_error = error
                time.sleep(1)
        raise TimeoutError(f"Catalog unavailable at {self.base_url}: {last_error}")

    def register(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/register", json=record)

    def register_service(
        self,
        name: str,
        description: str,
        endpoint: str | None = None,
        room_id: str | None = None,
        mqtt_topics: list[str] | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "type": "service",
            "name": name,
            "description": description,
            "mqtt_topics": mqtt_topics or [],
        }
        if endpoint:
            record["endpoint"] = endpoint
        if room_id:
            record["room_id"] = room_id
        return self.register(record)

    def register_device(
        self,
        device_id: str,
        kind: str,
        room_id: str,
        connector: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.register(
            {
                "type": "device",
                "device_id": device_id,
                "kind": kind,
                "room_id": room_id,
                "connector": connector,
                "metadata": metadata or {},
            }
        )

    def rooms(self) -> list[dict[str, Any]]:
        return self._request("GET", "/rooms")["rooms"]

    def room(self, room_id: str) -> dict[str, Any]:
        return self._request("GET", "/rooms", params={"room_id": room_id})["room"]

    def strategy(self, room_id: str) -> dict[str, Any]:
        return self._request("GET", f"/config/{room_id}")

