import pytest

from shared.senml import loads, make_pack, values
from shared.topics import (
    badge,
    emergency_command,
    environment,
    event_type_from_topic,
    prop,
    room_command,
    room_from_topic,
    session,
)


def test_canonical_topics_preserve_room_and_device_correlation():
    assert environment("room1", "env1") == "room/room1/environment/env1/telemetry"
    assert badge("room1", "b1", "position") == "game/room1/badge/b1/position"
    assert prop("room2", "typewriter", "interaction") == "game/room2/prop/typewriter/interaction"
    assert room_command("room1") == "command/room/room1"
    assert emergency_command("room2") == "command/emergency/room2"
    assert session("room1", "ended") == "session/room1/ended"
    assert room_from_topic("game/room2/prop/typewriter/interaction") == "room2"
    assert event_type_from_topic("game/room2/prop/typewriter/interaction") == "prop_interaction"


def test_invalid_topic_dimensions_are_rejected():
    with pytest.raises(ValueError):
        badge("room1", "b1", "unknown")
    with pytest.raises(ValueError):
        room_command("Room With Spaces")


def test_senml_round_trip_uses_base_name_and_base_time():
    pack = make_pack(
        "urn:escape-room:room1:environment:env1:",
        [("temperature", 22.5, "Cel"), ("humidity", 48.0, "%RH"), ("online", True, None)],
        timestamp=1234.5,
    )
    decoded = loads(pack)
    assert decoded[0]["name"].endswith(":temperature")
    assert decoded[1]["timestamp"] == 1234.5
    assert values(pack) == {"temperature": 22.5, "humidity": 48.0, "online": True}


@pytest.mark.parametrize("payload", [[], {}, [{"n": "temperature"}], [{"n": "x", "v": 1, "vs": "one"}]])
def test_malformed_senml_is_rejected(payload):
    with pytest.raises((TypeError, ValueError)):
        loads(payload)

