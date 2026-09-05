from services.web_dashboard.server import DashboardBridge
from shared.senml import make_pack


class FakeCatalog:
    def rooms(self):
        return [
            {
                "room_id": "room1",
                "name": "Test room",
                "theme": "Test",
                "dimensions": {"width_m": 10, "height_m": 8},
                "badges": [],
                "props": [],
            }
        ]


def test_dashboard_live_cache_decodes_senml_and_alerts():
    bridge = DashboardBridge(FakeCatalog())
    listener = bridge.add_listener()
    bridge.on_message(
        "room/room1/environment/env1/telemetry",
        __import__("json").dumps(make_pack("urn:test:", [("temperature", 23.0, "Cel")], 100.0)),
    )
    assert bridge.snapshot()["rooms"]["room1"]["environment"]["temperature"] == 23.0
    assert listener.get_nowait()["event_type"] == "environment"
    bridge.on_message(
        "system/alerts",
        '{"room_id":"room1","severity":"critical","message":"Fall","alert_type":"fall"}',
    )
    assert bridge.snapshot()["alerts"][0]["message"] == "Fall"
    bridge.remove_listener(listener)

