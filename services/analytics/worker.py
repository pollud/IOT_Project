"""Historical analytics engine consuming only the TimeSeries REST API."""

from __future__ import annotations

import logging
import os
import statistics
import threading
import time
from collections import Counter, defaultdict
from functools import wraps
from typing import Any

import cherrypy
import requests

from shared.catalog_client import CatalogClient
from shared.constants import DEFAULT_TIMESERIES_URL
from shared.http import server_config
from shared.mqtt import MQTTClient
from shared.senml import values as senml_values
from shared.topics import analytics_summary

LOGGER = logging.getLogger("analytics")

PERIOD_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}


def api_endpoint(function):
    """Map validation and dependency failures to stable HTTP API errors."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except cherrypy.HTTPError:
            raise
        except ValueError as error:
            raise cherrypy.HTTPError(400, str(error)) from error
        except requests.RequestException as error:
            raise cherrypy.HTTPError(502, f"TimeSeries or Catalog unavailable: {error}") from error

    return wrapped


def from_timestamp(period: str, now: float | None = None) -> float | None:
    if period == "all":
        return None
    if period not in PERIOD_SECONDS:
        raise ValueError("period must be one of: 1h, 24h, 7d, 30d, all")
    return (now or time.time()) - PERIOD_SECONDS[period]


class TimeSeriesClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = (base_url or os.getenv("TIMESERIES_URL", DEFAULT_TIMESERIES_URL)).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def events(
        self,
        room_id: str | None = None,
        event_type: str | None = None,
        from_ts: float | None = None,
        to_ts: float | None = None,
        order: str = "asc",
        max_items: int = 50000,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_size = min(2000, max_items)
        while len(records) < max_items:
            parameters: dict[str, Any] = {
                "limit": min(page_size, max_items - len(records)),
                "offset": len(records),
                "order": order,
            }
            if room_id:
                parameters["room_id"] = room_id
            if event_type:
                parameters["event_type"] = event_type
            if from_ts is not None:
                parameters["from_ts"] = from_ts
            if to_ts is not None:
                parameters["to_ts"] = to_ts
            response = self.session.get(f"{self.base_url}/events", params=parameters, timeout=self.timeout)
            response.raise_for_status()
            batch = response.json()["events"]
            records.extend(batch)
            if len(batch) < parameters["limit"]:
                break
        return records

    def health(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def reset(self) -> dict[str, Any]:
        response = self.session.post(f"{self.base_url}/reset", params={"confirm": "true"}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


class AnalyticsEngine:
    def __init__(self, timeseries: TimeSeriesClient, catalog: CatalogClient) -> None:
        self.timeseries = timeseries
        self.catalog = catalog

    @staticmethod
    def _measurements(event: dict[str, Any]) -> dict[str, Any]:
        payload = event.get("payload")
        if not isinstance(payload, list):
            return {}
        try:
            return senml_values(payload)
        except (TypeError, ValueError):
            return {}

    def room_stats(self, room_id: str, period: str = "24h") -> dict[str, Any]:
        events = self.timeseries.events(room_id, "session_ended", from_timestamp(period))
        durations = [
            float(event["payload"].get("duration_seconds", 0.0))
            for event in events
            if isinstance(event.get("payload"), dict) and event["payload"].get("duration_seconds") is not None
        ]
        successes = sum(
            1 for event in events if isinstance(event.get("payload"), dict) and event["payload"].get("success") is True
        )
        return {
            "room_id": room_id,
            "period": period,
            "total_sessions": len(events),
            "successful_sessions": successes,
            "completion_rate_percent": round(100.0 * successes / len(events), 2) if events else 0.0,
            "avg_solve_time_seconds": round(statistics.fmean(durations), 2) if durations else 0.0,
            "median_solve_time_seconds": round(statistics.median(durations), 2) if durations else 0.0,
            "min_solve_time_seconds": round(min(durations), 2) if durations else 0.0,
            "max_solve_time_seconds": round(max(durations), 2) if durations else 0.0,
        }

    def prop_stats(self, prop_id: str, room_id: str | None = None, period: str = "24h") -> dict[str, Any]:
        events = self.timeseries.events(room_id, "prop_interaction", from_timestamp(period))
        selected = [event for event in events if len(event["topic"].split("/")) >= 4 and event["topic"].split("/")[3] == prop_id]
        interaction_types = Counter()
        values = Counter()
        for event in selected:
            measurements = self._measurements(event)
            interaction_types[str(measurements.get("interaction_type", "unknown"))] += 1
            values[str(measurements.get("value", "unknown"))] += 1
        return {
            "prop_id": prop_id,
            "room_id": room_id,
            "period": period,
            "total_interactions": len(selected),
            "interaction_types": dict(interaction_types),
            "values": dict(values),
            "last_interaction_at": max((event["timestamp"] for event in selected), default=None),
        }

    def environment_stats(self, room_id: str, period: str = "24h") -> dict[str, Any]:
        events = self.timeseries.events(room_id, "environment", from_timestamp(period))
        series: dict[str, list[float]] = defaultdict(list)
        for event in events:
            for name, value in self._measurements(event).items():
                if name in {"temperature", "humidity", "co2", "voc"} and isinstance(value, int | float):
                    series[name].append(float(value))
        statistics_by_measurement = {
            name: {
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "avg": round(statistics.fmean(values), 3),
                "samples": len(values),
            }
            for name, values in series.items()
            if values
        }
        return {"room_id": room_id, "period": period, "measurements": statistics_by_measurement}

    def history(self, room_id: str, period: str = "24h", limit: int = 1000) -> dict[str, Any]:
        events = self.timeseries.events(
            room_id,
            "environment",
            from_timestamp(period),
            order="desc",
            max_items=min(max(1, limit), 5000),
        )
        points = [
            {"timestamp": event["timestamp"], **self._measurements(event)}
            for event in reversed(events)
        ]
        return {"room_id": room_id, "period": period, "history": points, "count": len(points)}

    def heatmap(self, room_id: str, period: str = "24h", grid_size: int = 10) -> dict[str, Any]:
        room = self.catalog.room(room_id)
        width = float(room["dimensions"]["width_m"])
        height = float(room["dimensions"]["height_m"])
        events = self.timeseries.events(room_id, "badge_position", from_timestamp(period))
        cells = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
        points: list[dict[str, Any]] = []
        for event in events:
            measurement = self._measurements(event)
            if not isinstance(measurement.get("x"), int | float) or not isinstance(measurement.get("y"), int | float):
                continue
            x = min(width, max(0.0, float(measurement["x"])))
            y = min(height, max(0.0, float(measurement["y"])))
            column = min(grid_size - 1, int((x / width) * grid_size))
            row = min(grid_size - 1, int((y / height) * grid_size))
            cells[row][column] += 1
            points.append({"timestamp": event["timestamp"], "badge_id": event["topic"].split("/")[3], "x": x, "y": y})
        return {
            "room_id": room_id,
            "period": period,
            "dimensions": {"width_m": width, "height_m": height},
            "grid_size": grid_size,
            "cells": cells,
            "samples": len(points),
            "latest_positions": self._latest_positions(points),
        }

    @staticmethod
    def _latest_positions(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for point in points:
            latest[point["badge_id"]] = point
        return list(latest.values())

    def bottlenecks(self, room_id: str | None = None, period: str = "7d") -> dict[str, Any]:
        events = self.timeseries.events(room_id, "game_transition", from_timestamp(period))
        grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
        for event in events:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            identifier = str(payload.get("trigger_id") or payload.get("from_state") or "unknown")
            grouped[(str(payload.get("room_id", event.get("room_id"))), identifier)].append(
                float(payload.get("elapsed_seconds", 0.0))
            )
        results = []
        for (event_room, identifier), durations in grouped.items():
            results.append(
                {
                    "room_id": event_room,
                    "puzzle": identifier,
                    "samples": len(durations),
                    "avg_solve_seconds": round(statistics.fmean(durations), 2),
                    "median_solve_seconds": round(statistics.median(durations), 2),
                    "max_solve_seconds": round(max(durations), 2),
                }
            )
        results.sort(key=lambda item: item["avg_solve_seconds"], reverse=True)
        return {"period": period, "bottlenecks": results}

    def safety(self, room_id: str | None = None, period: str = "24h") -> dict[str, Any]:
        alerts = self.timeseries.events(room_id, "alert", from_timestamp(period))
        rooms = [self.catalog.room(room_id)] if room_id else self.catalog.rooms()
        comfort_samples = 0
        comfortable = 0
        for room in rooms:
            events = self.timeseries.events(room["room_id"], "environment", from_timestamp(period))
            for event in events:
                values = self._measurements(event)
                required = {"temperature", "humidity", "co2", "voc"}
                if not required.issubset(values):
                    continue
                comfort_samples += 1
                if (
                    18 <= float(values["temperature"]) <= 26
                    and 30 <= float(values["humidity"]) <= 65
                    and float(values["co2"]) <= 1000
                    and float(values["voc"]) <= 1.0
                ):
                    comfortable += 1
        comfort_score = 100.0 * comfortable / comfort_samples if comfort_samples else 100.0
        alert_score = max(0.0, 100.0 - 12.5 * len(alerts))
        score = 0.8 * comfort_score + 0.2 * alert_score
        types = Counter(
            str(event["payload"].get("alert_type", "unknown"))
            for event in alerts
            if isinstance(event.get("payload"), dict)
        )
        return {
            "room_id": room_id,
            "period": period,
            "safety_score_percent": round(score, 2),
            "comfort_score_percent": round(comfort_score, 2),
            "environment_samples": comfort_samples,
            "total_alerts": len(alerts),
            "alerts_by_type": dict(types),
        }

    def maintenance(self, room_id: str | None = None, period: str = "7d") -> dict[str, Any]:
        battery_events = self.timeseries.events(room_id, "badge_battery", from_timestamp(period), order="desc")
        latest_battery: dict[str, float] = {}
        for event in battery_events:
            badge_id = event["topic"].split("/")[3]
            measurement = self._measurements(event)
            if badge_id not in latest_battery and isinstance(measurement.get("battery"), int | float):
                latest_battery[badge_id] = float(measurement["battery"])
        prop_events = self.timeseries.events(room_id, "prop_health", from_timestamp(period), order="desc")
        latest_props: dict[str, bool] = {}
        for event in prop_events:
            prop_id = event["topic"].split("/")[3]
            measurement = self._measurements(event)
            if prop_id not in latest_props:
                latest_props[prop_id] = bool(measurement.get("online", False))
        warnings = [
            {"component_id": badge_id, "type": "badge", "reason": "low_battery", "value": round(level, 2)}
            for badge_id, level in latest_battery.items()
            if level < 20.0
        ]
        warnings.extend(
            {"component_id": prop_id, "type": "prop", "reason": "offline", "value": False}
            for prop_id, online in latest_props.items()
            if not online
        )
        return {
            "room_id": room_id,
            "period": period,
            "latest_badge_battery": latest_battery,
            "latest_prop_status": latest_props,
            "maintenance_required": warnings,
        }

    def game_center(self, period: str = "24h") -> dict[str, Any]:
        rooms = self.catalog.rooms()
        per_room = [self.room_stats(room["room_id"], period) for room in rooms]
        total_sessions = sum(item["total_sessions"] for item in per_room)
        total_successes = sum(item["successful_sessions"] for item in per_room)
        weighted_duration = sum(item["avg_solve_time_seconds"] * item["total_sessions"] for item in per_room)
        if period == "all":
            ended = self.timeseries.events(event_type="session_ended")
            if len(ended) >= 2:
                window_hours = max((ended[-1]["timestamp"] - ended[0]["timestamp"]) / 3600.0, 1 / 60)
            else:
                window_hours = 1.0
        else:
            window_hours = PERIOD_SECONDS[period] / 3600.0
        player_count = sum(len(room.get("badges", [])) for room in rooms)
        average_players = player_count / len(rooms) if rooms else 0.0
        return {
            "period": period,
            "rooms": per_room,
            "kpis": {
                "configured_rooms": len(rooms),
                "total_sessions": total_sessions,
                "successful_sessions": total_successes,
                "completion_rate_percent": round(100.0 * total_successes / total_sessions, 2) if total_sessions else 0.0,
                "overall_avg_duration_seconds": round(weighted_duration / total_sessions, 2) if total_sessions else 0.0,
                "games_per_hour": round(total_sessions / window_hours, 3),
                "estimated_players_per_hour": round((total_sessions * average_players) / window_hours, 3),
            },
        }


class AnalyticsService:
    def __init__(self, engine: AnalyticsEngine, catalog: CatalogClient) -> None:
        self.engine = engine
        self.catalog = catalog
        self._stop = threading.Event()
        self.mqtt = MQTTClient("analytics", heartbeat_payload={"role": "historical_analytics"})
        self.mqtt.on_message_callback = self.on_session_ended

    def start(self) -> None:
        self.catalog.register_service(
            name="analytics",
            description="Historical game, player, environment and safety analytics",
            endpoint=os.getenv("SERVICE_URL", "http://analytics:8086"),
            mqtt_topics=["session/+/ended", "analytics/+/summary"],
        )
        self.mqtt.subscribe("session/+/ended", qos=1)
        self.mqtt.start()

    def stop(self) -> None:
        self._stop.set()
        self.mqtt.stop()

    def on_session_ended(self, topic: str, payload: str) -> None:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "session" or parts[2] != "ended":
            return
        threading.Thread(target=self._publish_summary, args=(parts[1],), daemon=True).start()

    def _publish_summary(self, room_id: str) -> None:
        if self._stop.wait(0.75):
            return
        try:
            self.mqtt.publish(analytics_summary(room_id), self.engine.room_stats(room_id, "all"), qos=1)
        except (requests.RequestException, RuntimeError, ValueError):
            LOGGER.exception("Could not publish post-session analytics for %s", room_id)


class StatsRoute:
    def __init__(self, service: AnalyticsService) -> None:
        self.service = service

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def room(self, room_id: str, period: str = "24h"):
        return self.service.engine.room_stats(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def prop(self, prop_id: str, room_id: str | None = None, period: str = "24h"):
        return self.service.engine.prop_stats(prop_id, room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def environment(self, room_id: str, period: str = "24h"):
        return self.service.engine.environment_stats(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def history(self, room_id: str, period: str = "24h", limit: str = "1000"):
        return self.service.engine.history(room_id, period, int(limit))

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def heatmap(self, room_id: str, period: str = "24h"):
        return self.service.engine.heatmap(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def bottlenecks(self, room_id: str | None = None, period: str = "7d"):
        return self.service.engine.bottlenecks(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def safety(self, room_id: str | None = None, period: str = "24h"):
        return self.service.engine.safety(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def maintenance(self, room_id: str | None = None, period: str = "7d"):
        return self.service.engine.maintenance(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def game_center(self, period: str = "24h"):
        return self.service.engine.game_center(period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    @api_endpoint
    def reset(self):
        if cherrypy.request.method.upper() != "POST":
            raise cherrypy.HTTPError(405, "POST required")
        return self.service.engine.timeseries.reset()


class Root:
    def __init__(self, service: AnalyticsService) -> None:
        self.service = service
        self.stats = StatsRoute(service)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def health(self):
        try:
            timeseries = self.service.engine.timeseries.health()
            status = "ok"
        except requests.RequestException as error:
            timeseries = {"error": str(error)}
            status = "degraded"
        return {"status": status, "mqtt_connected": self.service.mqtt.connected, "timeseries": timeseries}


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    catalog = CatalogClient()
    catalog.wait_until_ready()
    engine = AnalyticsEngine(TimeSeriesClient(), catalog)
    service = AnalyticsService(engine, catalog)
    service.start()
    cherrypy.engine.subscribe("stop", service.stop)
    cherrypy.config.update(server_config(8086))
    cherrypy.quickstart(Root(service))


if __name__ == "__main__":
    main()
