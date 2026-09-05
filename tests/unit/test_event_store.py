import json
import threading
import time

from services.timeseries_adapter.adapter import EventStore, StoredEvent, TimeSeriesAdapter


def event(timestamp, room, event_type, topic, payload):
    return StoredEvent(timestamp, room, event_type, topic, json.dumps(payload))


def test_event_store_filters_orders_prunes_and_resets(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.insert_batch(
        [
            event(3, "room2", "environment", "room/room2/environment/env1/telemetry", [{"n": "x", "v": 3}]),
            event(1, "room1", "environment", "room/room1/environment/env1/telemetry", [{"n": "x", "v": 1}]),
            event(2, "room1", "session_ended", "session/room1/ended", {"success": True}),
        ]
    )
    room1 = store.query(room_id="room1")
    assert [item["timestamp"] for item in room1] == [1, 2]
    assert store.query(event_type="session_ended")[0]["payload"]["success"] is True
    assert store.prune(2) == 1
    assert store.count() == 2
    store.reset()
    assert store.count() == 0


def test_adapter_reset_is_an_ordered_queue_barrier(tmp_path):
    store = EventStore(tmp_path / "barrier.db")
    adapter = TimeSeriesAdapter(store, catalog=object())
    adapter.batch_size = 1
    adapter.flush_interval = 0.01
    adapter.writer = threading.Thread(target=adapter._writer_loop, daemon=True)
    adapter.writer.start()
    try:
        adapter.queue.put(event(1, "room1", "before_reset", "session/room1/started", {"sequence": 1}))
        adapter.reset()
        adapter.queue.put(event(2, "room1", "after_reset", "session/room1/started", {"sequence": 2}))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and store.count() != 1:
            time.sleep(0.01)
        records = store.query()
        assert [record["event_type"] for record in records] == ["after_reset"]
    finally:
        adapter.stop()
