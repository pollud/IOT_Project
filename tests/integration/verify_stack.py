"""Black-box verification of the complete Docker Compose stack.

Run after ``docker compose up --build -d``. The script returns a non-zero exit
code on the first failed contract; it never treats an HTTP acknowledgement as
proof unless the downstream MQTT/state/persistence effect is observed.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import requests

CATALOG = "http://localhost:8080"
TIMESERIES = "http://localhost:8085"
ANALYTICS = "http://localhost:8086"
DASHBOARD = "http://localhost:8087"


def request_json(method: str, url: str, **kwargs) -> dict[str, Any]:
    response = requests.request(method, url, timeout=8, **kwargs)
    response.raise_for_status()
    return response.json()


def expect_status(method: str, url: str, expected: int, **kwargs) -> requests.Response:
    response = requests.request(method, url, timeout=8, **kwargs)
    if response.status_code != expected:
        raise AssertionError(
            f"Expected HTTP {expected} for {method} {url}, got {response.status_code}: {response.text[:500]}"
        )
    return response


def wait_http(url: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            request_json("GET", url)
            return
        except requests.RequestException as current:
            error = current
            time.sleep(1)
    raise AssertionError(f"Service did not become healthy: {url}: {error}")


def wait_until(label: str, predicate: Callable[[], Any], timeout: float = 15, interval: float = 0.25) -> Any:
    deadline = time.monotonic() + timeout
    last_value: Any = None
    while time.monotonic() < deadline:
        last_value = predicate()
        if last_value:
            print(f"PASS  {label}")
            return last_value
        time.sleep(interval)
    raise AssertionError(f"Timeout: {label}; last value={last_value!r}")


class SSEObserver:
    def __init__(self) -> None:
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.stop = threading.Event()
        self.connected = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.response: requests.Response | None = None

    def start(self) -> None:
        self.thread.start()
        if not self.connected.wait(10):
            raise AssertionError("SSE stream did not connect")

    def _run(self) -> None:
        try:
            self.response = requests.get(f"{DASHBOARD}/api/stream", stream=True, timeout=(5, 60))
            self.response.raise_for_status()
            self.connected.set()
            event_type = "message"
            for raw_line in self.response.iter_lines(decode_unicode=True, chunk_size=1):
                if self.stop.is_set():
                    break
                line = raw_line or ""
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    self.events.put({"event": event_type, "data": json.loads(line.split(":", 1)[1].strip())})
        except (requests.RequestException, AttributeError, OSError):
            # Closing a streaming response interrupts urllib3's active read.
            # That is the expected shutdown path after all assertions complete.
            if not self.stop.is_set():
                raise
        finally:
            self.connected.set()

    def wait_for_topic(self, topic: str, timeout: float = 15) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            if event["event"] == "mqtt" and event["data"].get("topic") == topic:
                return event["data"]
        return None

    def close(self) -> None:
        self.stop.set()
        if self.response:
            self.response.close()
        self.thread.join(timeout=2)


def room_status(room_id: str) -> dict[str, Any]:
    snapshot = request_json("GET", f"{DASHBOARD}/api/status")
    return snapshot["rooms"][room_id].get("status") or {}


def command(room_id: str, name: str, **fields) -> dict[str, Any]:
    payload = {"room_id": room_id, "command": name, **fields}
    result = request_json(
        "POST",
        f"{DASHBOARD}/api/command",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
    )
    assert result["accepted"] is True
    return result


def main() -> None:
    for endpoint in (
        f"{CATALOG}/health",
        f"{TIMESERIES}/health",
        f"{ANALYTICS}/health",
        f"{DASHBOARD}/api/health",
    ):
        wait_http(endpoint)
        print(f"PASS  healthy {endpoint}")

    rooms_response = expect_status("GET", f"{CATALOG}/rooms", 200)
    assert not rooms_response.history, "Catalog collection endpoints must not redirect and lose POST bodies"
    catalog_rooms = rooms_response.json()["rooms"]
    assert [room["room_id"] for room in catalog_rooms] == ["room1", "room2"]
    expected = {
        "catalog",
        "environment_connector_room1",
        "environment_connector_room2",
        "room_actuator_connector_room1",
        "room_actuator_connector_room2",
        "badge_connector_room1",
        "badge_connector_room2",
        "prop_connector_room1",
        "prop_connector_room2",
        "room_control_room1",
        "room_control_room2",
        "safety_monitor",
        "timeseries_adapter",
        "analytics",
        "web_dashboard",
    }

    def registered_inventory():
        services = request_json("GET", f"{CATALOG}/services")["services"]
        devices = request_json("GET", f"{CATALOG}/devices")["devices"]
        service_names = [service["name"] for service in services]
        if len(service_names) != len(set(service_names)):
            raise AssertionError("Catalog contains duplicate service names")
        if expected.issubset(service_names) and len(devices) >= 14:
            return {"services": services, "devices": devices}
        return None

    wait_until("Catalog self-registration, CRUD data and correlations", registered_inventory, timeout=30)

    probe = {"type": "service", "name": "integration_probe", "description": "Temporary CRUD probe"}
    created = expect_status("POST", f"{CATALOG}/services", 201, json=probe).json()["service"]
    assert created["name"] == probe["name"]
    expect_status("POST", f"{CATALOG}/services", 409, json=probe)
    probe["description"] = "Updated CRUD probe"
    updated = expect_status("PUT", f"{CATALOG}/services?name=integration_probe", 200, json=probe).json()["service"]
    assert updated["description"] == probe["description"]
    expect_status("DELETE", f"{CATALOG}/services?name=integration_probe", 200)
    expect_status("GET", f"{CATALOG}/services?name=integration_probe", 404)

    strategy = request_json("GET", f"{CATALOG}/config/room1")
    invalid_strategy = deepcopy(strategy)
    invalid_strategy["states"][invalid_strategy["initial_state"]]["transitions"][0]["target_state"] = "missing_state"
    expect_status("PUT", f"{CATALOG}/config/room1", 400, json=invalid_strategy)
    assert request_json("GET", f"{CATALOG}/config/room1")["version"] == strategy["version"]
    print("PASS  Catalog REST CRUD statuses and atomic strategy rejection")

    dashboard_page = expect_status("GET", DASHBOARD, 200)
    assert "Content-Security-Policy" in dashboard_page.headers
    assert "Escape Room IoT Command Center" in dashboard_page.text
    invalid_content_type = expect_status("POST", f"{DASHBOARD}/api/command", 415, data="{}")
    assert invalid_content_type.headers["Content-Type"] == "application/json"
    assert invalid_content_type.json()["error"]["status"] == 415
    expect_status(
        "POST",
        f"{DASHBOARD}/api/command",
        404,
        json={"room_id": "missing_room", "command": "reset"},
    )
    expect_status(
        "POST",
        f"{DASHBOARD}/api/command",
        400,
        json={
            "room_id": "room1",
            "command": "trigger_prop",
            "prop_id": "pipboy",
            "interaction_type": "rfid",
            "value": "wrong_value",
        },
    )
    expect_status("GET", f"{ANALYTICS}/stats/room?room_id=room1&period=invalid", 400)
    expect_status("POST", f"{TIMESERIES}/reset", 400)
    print("PASS  dashboard security headers and negative API validation")

    observer = SSEObserver()
    observer.start()
    try:
        request_json("POST", f"{DASHBOARD}/api/stats/reset")
        command("room1", "reset")
        command("room2", "reset")
        wait_until("room1 reset reaches initial state", lambda: room_status("room1").get("current_state") == "vault_door_sealed")
        wait_until("room2 reset reaches initial state", lambda: room_status("room2").get("current_state") == "mansion_hall")

        command("room1", "trigger_prop", prop_id="pipboy", interaction_type="rfid", value="scanned")
        wait_until("dashboard prop command reaches room1 FSM", lambda: room_status("room1").get("current_state") == "overseer_office")
        command("room1", "trigger_prop", prop_id="terminal", interaction_type="button", value="hacked")
        wait_until("timed FSM transition fires", lambda: room_status("room1").get("current_state") == "wasteland_exit", timeout=6)
        command("room1", "trigger_prop", prop_id="geiger_counter", interaction_type="capacitive", value="touched")
        wait_until("room1 session completes", lambda: room_status("room1").get("completed") is True)
        assert room_status("room2").get("current_state") == "mansion_hall"
        print("PASS  two-room isolation")

        assert observer.wait_for_topic("game/room1/transition", timeout=10)
        print("PASS  frontend SSE receives real MQTT events")

        def persisted_session():
            result = request_json("GET", f"{TIMESERIES}/events?room_id=room1&event_type=session_ended")
            return result["events"]

        wait_until("session end is persisted through MQTT", persisted_session)
        analytics = wait_until(
            "analytics reads persisted history through REST",
            lambda: request_json("GET", f"{ANALYTICS}/stats/room?room_id=room1&period=all")["total_sessions"] >= 1,
        )
        assert analytics is True
        heatmap = wait_until(
            "badge position produces a non-empty heatmap",
            lambda: request_json("GET", f"{ANALYTICS}/stats/heatmap?room_id=room1&period=all")["samples"] > 0,
        )
        assert heatmap is True

        request_json("POST", "http://localhost:8103/force_fall?badge_id=b1")
        assert observer.wait_for_topic("system/alerts", timeout=10)
        wait_until(
            "safety monitor independently unlocks the room",
            lambda: request_json("GET", "http://localhost:8102/health")["actuators"]["door_locked"] is False,
        )
        alerts = request_json("GET", f"{DASHBOARD}/api/status")["alerts"]
        assert any(alert.get("alert_type") == "fall" and alert.get("room_id") == "room1" for alert in alerts)
        print("PASS  live GUI alert replaces Telegram notification path")
    finally:
        observer.close()

    print("\nAll end-to-end checks passed.")


if __name__ == "__main__":
    main()
