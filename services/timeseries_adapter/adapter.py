"""MQTT-to-SQLite persistence adapter with an independent REST query API."""

from __future__ import annotations

import json
import logging
import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cherrypy

from shared.catalog_client import CatalogClient
from shared.config import env_float, env_int
from shared.http import server_config
from shared.mqtt import MQTTClient
from shared.senml import loads as load_senml
from shared.topics import (
    SERVICE_STATUS_WILDCARD,
    SYSTEM_ALERTS,
    badge_wildcard,
    environment_wildcard,
    event_type_from_topic,
    room_from_topic,
)

LOGGER = logging.getLogger("timeseries_adapter")


@dataclass(frozen=True)
class StoredEvent:
    timestamp: float
    room_id: str | None
    event_type: str
    topic: str
    payload: str


@dataclass
class ResetRequest:
    """Queue barrier ensuring all pre-reset events are removed atomically."""

    done: threading.Event = field(default_factory=threading.Event)
    error: sqlite3.Error | None = None


class EventStore:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    room_id TEXT,
                    event_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_room_time ON events(room_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, timestamp);
                CREATE INDEX IF NOT EXISTS idx_events_topic_time ON events(topic, timestamp);
                """
            )

    def insert_batch(self, events: list[StoredEvent]) -> None:
        if not events:
            return
        with self.connect() as connection:
            connection.executemany(
                "INSERT INTO events(timestamp, room_id, event_type, topic, payload) VALUES (?, ?, ?, ?, ?)",
                [(event.timestamp, event.room_id, event.event_type, event.topic, event.payload) for event in events],
            )

    def query(
        self,
        room_id: str | None = None,
        event_type: str | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
        limit: int = 500,
        offset: int = 0,
        order: str = "asc",
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if room_id:
            conditions.append("room_id = ?")
            parameters.append(room_id)
        if event_type:
            conditions.append("event_type = ?")
            parameters.append(event_type)
        if from_ts is not None:
            conditions.append("timestamp >= ?")
            parameters.append(from_ts)
        if to_ts is not None:
            conditions.append("timestamp <= ?")
            parameters.append(to_ts)
        direction = "DESC" if order.lower() == "desc" else "ASC"
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        # Column names and direction come only from this method's fixed allow-list;
        # every user-controlled filter value remains a bound SQLite parameter.
        sql = (  # nosec B608
            "SELECT id, timestamp, room_id, event_type, topic, payload FROM events"  # nosec B608
            f"{where} ORDER BY timestamp {direction}, id {direction} LIMIT ? OFFSET ?"
        )
        parameters.extend([limit, offset])
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def prune(self, cutoff: float) -> int:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
            return int(cursor.rowcount)

    def reset(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM events")


class TimeSeriesAdapter:
    def __init__(self, store: EventStore, catalog: CatalogClient) -> None:
        self.store = store
        self.catalog = catalog
        self.queue: queue.Queue[StoredEvent | ResetRequest | None] = queue.Queue(
            maxsize=env_int("QUEUE_SIZE", 20000, 100)
        )
        self.batch_size = env_int("BATCH_SIZE", 100, 1)
        self.flush_interval = env_float("FLUSH_INTERVAL_SECONDS", 0.5, minimum=0.05)
        self.retention_days = env_int("RETENTION_DAYS", 30, 1)
        self._stop = threading.Event()
        self.writer: threading.Thread | None = None
        self.retention: threading.Thread | None = None
        self.accepted = 0
        self.rejected = 0
        self.mqtt = MQTTClient(
            "timeseries_adapter",
            heartbeat_payload=lambda: {"queued_events": self.queue.qsize(), "stored_events": self.store.count()},
        )
        self.mqtt.on_message_callback = self.on_message

    @staticmethod
    def subscriptions() -> list[tuple[str, int]]:
        return [
            (environment_wildcard(), 0),
            (badge_wildcard(), 0),
            ("game/+/prop/+/+", 0),
            ("game/+/status", 1),
            ("game/+/transition", 1),
            ("session/+/+", 1),
            (SYSTEM_ALERTS, 1),
            ("command/room/+", 1),
            ("command/emergency/+", 1),
            (SERVICE_STATUS_WILDCARD, 1),
        ]

    def start(self) -> None:
        self.catalog.register_service(
            name="timeseries_adapter",
            description="MQTT telemetry persistence and historical REST API",
            endpoint=os.getenv("SERVICE_URL", "http://timeseries_adapter:8085"),
            mqtt_topics=[topic for topic, _ in self.subscriptions()],
        )
        for topic, qos in self.subscriptions():
            self.mqtt.subscribe(topic, qos=qos)
        self.mqtt.start()
        self.writer = threading.Thread(target=self._writer_loop, name="timeseries-writer", daemon=True)
        self.retention = threading.Thread(target=self._retention_loop, name="timeseries-retention", daemon=True)
        self.writer.start()
        self.retention.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass
        if self.writer:
            self.writer.join(timeout=10)
        if self.retention:
            self.retention.join(timeout=2)
        self.mqtt.stop()

    def reset(self, timeout: float = 10.0) -> None:
        """Reset storage at an ordered queue barrier.

        Events accepted before the request are flushed and then deleted; events
        accepted afterwards remain valid live telemetry and are stored normally.
        """
        request = ResetRequest()
        self.queue.put(request, timeout=min(timeout, 2.0))
        if not request.done.wait(timeout):
            raise TimeoutError("Timed out while resetting TimeSeries storage")
        if request.error:
            raise request.error

    @staticmethod
    def _event_timestamp(topic: str, parsed: Any) -> float:
        if isinstance(parsed, list):
            try:
                return float(load_senml(parsed)[0]["timestamp"])
            except (ValueError, TypeError, IndexError):
                return time.time()
        if isinstance(parsed, dict):
            for key in ("timestamp", "updated_at", "state_entered_at"):
                if key in parsed:
                    return float(parsed[key])
        return time.time()

    def on_message(self, topic: str, payload: str) -> None:
        try:
            parsed = json.loads(payload)
            if not isinstance(parsed, dict | list):
                raise TypeError("MQTT payload must be a JSON object or SenML array")
            if isinstance(parsed, list):
                load_senml(parsed)
            room_id = room_from_topic(topic)
            if topic == SYSTEM_ALERTS and isinstance(parsed, dict):
                room_id = parsed.get("room_id")
            event = StoredEvent(
                timestamp=self._event_timestamp(topic, parsed),
                room_id=room_id,
                event_type=event_type_from_topic(topic),
                topic=topic,
                payload=json.dumps(parsed, separators=(",", ":")),
            )
            self.queue.put(event, timeout=1.0)
            self.accepted += 1
        except (ValueError, TypeError, json.JSONDecodeError, queue.Full):
            self.rejected += 1
            LOGGER.warning("Rejected event on %s", topic)

    def _writer_loop(self) -> None:
        batch: list[StoredEvent] = []
        deadline = time.monotonic() + self.flush_interval
        while not self._stop.is_set() or not self.queue.empty() or batch:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                item = self.queue.get(timeout=timeout)
                if isinstance(item, StoredEvent):
                    batch.append(item)
                elif isinstance(item, ResetRequest):
                    try:
                        if batch:
                            self.store.insert_batch(batch)
                            batch.clear()
                        self.store.reset()
                    except sqlite3.Error as error:
                        item.error = error
                    finally:
                        item.done.set()
                self.queue.task_done()
            except queue.Empty:
                pass
            if batch and (len(batch) >= self.batch_size or time.monotonic() >= deadline or self._stop.is_set()):
                try:
                    self.store.insert_batch(batch)
                    batch.clear()
                except sqlite3.Error:
                    LOGGER.exception("SQLite batch write failed; retrying")
                    time.sleep(0.25)
                deadline = time.monotonic() + self.flush_interval

    def _retention_loop(self) -> None:
        while not self._stop.wait(3600):
            cutoff = time.time() - self.retention_days * 86400
            removed = self.store.prune(cutoff)
            if removed:
                LOGGER.info("Pruned %s expired events", removed)


class Root:
    def __init__(self, adapter: TimeSeriesAdapter) -> None:
        self.adapter = adapter

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        return {
            "status": "ok" if self.adapter.mqtt.connected else "degraded",
            "stored_events": self.adapter.store.count(),
            "queued_events": self.adapter.queue.qsize(),
            "accepted": self.adapter.accepted,
            "rejected": self.adapter.rejected,
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def events(
        self,
        room_id: str | None = None,
        event_type: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        limit: str = "500",
        offset: str = "0",
        order: str = "asc",
    ):
        if cherrypy.request.method.upper() != "GET":
            raise cherrypy.HTTPError(405, "GET required")
        try:
            parsed_limit = min(5000, max(1, int(limit)))
            parsed_offset = max(0, int(offset))
            if order not in {"asc", "desc"}:
                raise ValueError("order must be asc or desc")
            records = self.adapter.store.query(
                room_id=room_id,
                event_type=event_type,
                from_ts=float(from_ts) if from_ts is not None else None,
                to_ts=float(to_ts) if to_ts is not None else None,
                limit=parsed_limit,
                offset=parsed_offset,
                order=order,
            )
        except ValueError as error:
            raise cherrypy.HTTPError(400, str(error)) from error
        return {"events": records, "count": len(records), "limit": parsed_limit, "offset": parsed_offset}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def reset(self, confirm: str = "false"):
        if cherrypy.request.method.upper() != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        if confirm.lower() != "true":
            raise cherrypy.HTTPError(400, "confirm=true is required")
        try:
            self.adapter.reset()
        except (queue.Full, TimeoutError, sqlite3.Error) as error:
            raise cherrypy.HTTPError(503, f"Reset unavailable: {error}") from error
        return {"success": True}


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    store = EventStore(os.getenv("DATABASE_PATH", "/var/lib/timeseries/events.db"))
    adapter = TimeSeriesAdapter(store, catalog)
    adapter.start()
    cherrypy.engine.subscribe("stop", adapter.stop)
    cherrypy.config.update(server_config(8085))
    cherrypy.quickstart(Root(adapter))


if __name__ == "__main__":
    main()
