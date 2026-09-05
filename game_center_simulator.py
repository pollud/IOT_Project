"""Play every configured room through the same public Dashboard REST API."""

from __future__ import annotations

import concurrent.futures
import os
import time
from typing import Any

import requests

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8087").rstrip("/")


def request_json(method: str, path: str, **kwargs) -> dict[str, Any]:
    response = requests.request(method, f"{DASHBOARD_URL}{path}", timeout=8, **kwargs)
    response.raise_for_status()
    return response.json()


def status(room_id: str) -> dict[str, Any]:
    return request_json("GET", "/api/status")["rooms"][room_id].get("status") or {}


def wait_state(room_id: str, expected: str, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if status(room_id).get("current_state") == expected:
            return
        time.sleep(0.2)
    raise TimeoutError(f"{room_id} did not reach {expected}")


def command(room_id: str, command_name: str, **parameters) -> None:
    response = request_json(
        "POST",
        "/api/command",
        json={"room_id": room_id, "command": command_name, **parameters},
    )
    if not response.get("accepted"):
        raise RuntimeError(f"Command was not accepted: {response}")


def play_room(room_id: str) -> str:
    strategy = request_json("GET", f"/api/strategy/{room_id}")
    command(room_id, "reset")
    current = strategy["initial_state"]
    wait_state(room_id, current)
    print(f"[{room_id}] session started in {current}")

    visited = set()
    while not strategy["states"][current].get("is_terminal"):
        if current in visited:
            raise RuntimeError(f"Cycle detected while simulating {room_id}: {current}")
        visited.add(current)
        transitions = strategy["states"][current]["transitions"]
        if not transitions:
            raise RuntimeError(f"Non-terminal state has no transitions: {room_id}/{current}")
        transition = transitions[0]
        target = transition["target_state"]
        if transition["trigger"] == "event":
            command(
                room_id,
                "trigger_prop",
                prop_id=transition["prop_id"],
                interaction_type=transition["interaction_type"],
                value=str(transition["value"]),
            )
        else:
            time.sleep(float(transition["duration_seconds"]) + 0.25)
        wait_state(room_id, target)
        print(f"[{room_id}] {current} -> {target} ({transition['trigger']})")
        current = target
    return room_id


def main() -> None:
    rooms = request_json("GET", "/api/rooms")["rooms"]
    room_ids = [room["room_id"] for room in rooms]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(room_ids)) as executor:
        completed = list(executor.map(play_room, room_ids))
    print(f"Completed rooms independently: {', '.join(completed)}")


if __name__ == "__main__":
    main()

