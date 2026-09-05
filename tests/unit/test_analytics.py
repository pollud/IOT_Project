from services.analytics.worker import AnalyticsEngine
from shared.senml import make_pack


class FakeTimeSeries:
    def __init__(self, events):
        self.all_events = events

    def events(self, room_id=None, event_type=None, from_ts=None, to_ts=None, order="asc", max_items=50000):
        selected = [
            item
            for item in self.all_events
            if (room_id is None or item.get("room_id") == room_id)
            and (event_type is None or item.get("event_type") == event_type)
            and (from_ts is None or item["timestamp"] >= from_ts)
            and (to_ts is None or item["timestamp"] <= to_ts)
        ]
        selected.sort(key=lambda item: item["timestamp"], reverse=order == "desc")
        return selected[:max_items]


class FakeCatalog:
    def __init__(self):
        self._rooms = [
            {"room_id": "room1", "dimensions": {"width_m": 10, "height_m": 8}, "badges": [{}, {}]},
            {"room_id": "room2", "dimensions": {"width_m": 9, "height_m": 9}, "badges": [{}, {}]},
        ]

    def rooms(self):
        return self._rooms

    def room(self, room_id):
        return next(room for room in self._rooms if room["room_id"] == room_id)


def sample_events(now):
    return [
        {
            "timestamp": now - 50,
            "room_id": "room1",
            "event_type": "session_ended",
            "topic": "session/room1/ended",
            "payload": {"duration_seconds": 300, "success": True},
        },
        {
            "timestamp": now - 30,
            "room_id": "room1",
            "event_type": "session_ended",
            "topic": "session/room1/ended",
            "payload": {"duration_seconds": 420, "success": False},
        },
        {
            "timestamp": now - 25,
            "room_id": "room1",
            "event_type": "environment",
            "topic": "room/room1/environment/env1/telemetry",
            "payload": make_pack("urn:test:", [("temperature", 22, "Cel"), ("humidity", 45, "%RH"), ("co2", 700, "ppm"), ("voc", 0.4, "mg/m3")], now - 25),
        },
        {
            "timestamp": now - 20,
            "room_id": "room1",
            "event_type": "badge_position",
            "topic": "game/room1/badge/b1/position",
            "payload": make_pack("urn:test:", [("x", 5, "m"), ("y", 4, "m")], now - 20),
        },
        {
            "timestamp": now - 10,
            "room_id": "room1",
            "event_type": "game_transition",
            "topic": "game/room1/transition",
            "payload": {"room_id": "room1", "trigger_id": "pipboy", "elapsed_seconds": 75},
        },
    ]


def test_historical_analytics_math(monkeypatch):
    now = 10_000.0
    monkeypatch.setattr("services.analytics.worker.time.time", lambda: now)
    engine = AnalyticsEngine(FakeTimeSeries(sample_events(now)), FakeCatalog())
    room = engine.room_stats("room1", "24h")
    assert room["total_sessions"] == 2
    assert room["completion_rate_percent"] == 50
    assert room["avg_solve_time_seconds"] == 360
    assert engine.environment_stats("room1", "24h")["measurements"]["co2"]["avg"] == 700
    heatmap = engine.heatmap("room1", "24h")
    assert heatmap["samples"] == 1
    assert heatmap["latest_positions"][0]["badge_id"] == "b1"
    bottlenecks = engine.bottlenecks("room1", "24h")["bottlenecks"]
    assert bottlenecks[0]["puzzle"] == "pipboy"
    assert bottlenecks[0]["avg_solve_seconds"] == 75
    assert engine.safety("room1", "24h")["safety_score_percent"] == 100

