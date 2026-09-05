import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pytest

from services.room_control.fsm import RoomFSM
from shared.fsm_schema import validate_strategy


class FakeMQTT:
    def __init__(self):
        self.messages = []

    def publish(self, topic, payload, qos=0, retain=False, wait=False):
        if is_dataclass(payload):
            payload = asdict(payload)
        self.messages.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})


class FakeClock:
    def __init__(self, current=1000.0):
        self.current = current

    def __call__(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


@pytest.fixture
def room1_strategy():
    return json.loads(Path("config/strategy_room1.json").read_text(encoding="utf-8"))


def test_repository_strategies_are_semantically_valid():
    for room_id in ("room1", "room2"):
        strategy = json.loads(Path(f"config/strategy_{room_id}.json").read_text(encoding="utf-8"))
        validate_strategy(strategy)


def test_schema_rejects_unknown_target(room1_strategy):
    room1_strategy["states"]["vault_door_sealed"]["transitions"][0]["target_state"] = "missing"
    with pytest.raises(ValueError, match="unknown state"):
        validate_strategy(room1_strategy)


def test_fsm_completes_with_real_duration_and_transition_events(room1_strategy):
    mqtt = FakeMQTT()
    clock = FakeClock()
    fsm = RoomFSM("room1", room1_strategy, mqtt, clock=clock)
    fsm.start()
    assert fsm.current_state == "vault_door_sealed"
    assert any(message["topic"] == "session/room1/started" for message in mqtt.messages)

    clock.advance(12)
    assert fsm.event_transition("pipboy", "rfid", "scanned")
    clock.advance(20)
    assert fsm.event_transition("terminal", "button", "hacked")
    assert fsm.current_state == "vault_door_opening"
    clock.advance(2)
    assert fsm.time_transition("vault_door_opening", "wasteland_exit")
    clock.advance(8)
    assert fsm.event_transition("geiger_counter", "capacitive", "touched")

    assert fsm.current_state == "game_cleared"
    assert fsm.completed is True
    ended = next(message for message in reversed(mqtt.messages) if message["topic"] == "session/room1/ended")
    assert ended["payload"]["duration_seconds"] == 42
    transitions = [message for message in mqtt.messages if message["topic"] == "game/room1/transition"]
    assert [message["payload"]["to_state"] for message in transitions] == [
        "overseer_office",
        "vault_door_opening",
        "wasteland_exit",
        "game_cleared",
    ]
    fsm.close()


def test_recovery_keeps_session_and_does_not_replay_actuator_actions(room1_strategy):
    mqtt = FakeMQTT()
    recovered = {
        "room_id": "room1",
        "session_id": "room1-sessionabc",
        "current_state": "overseer_office",
        "strategy_version": room1_strategy["version"],
        "started_at": 900.0,
        "state_entered_at": 950.0,
        "completed": False,
    }
    fsm = RoomFSM("room1", room1_strategy, mqtt, recovered_status=recovered, clock=FakeClock())
    fsm.start()
    assert fsm.recovered is True
    assert fsm.current_state == "overseer_office"
    assert fsm.session_id == "room1-sessionabc"
    assert not any(message["topic"] == "command/room/room1" for message in mqtt.messages)
    assert mqtt.messages[-1]["topic"] == "game/room1/status"
    fsm.close()

