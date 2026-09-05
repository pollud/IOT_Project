import json
import shutil
from types import SimpleNamespace

import cherrypy
import pytest
import requests

from services.catalog.catalog import CatalogStore, Root
from shared.http import json_error_page


@pytest.fixture
def store(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    for filename in ("catalog.json", "rooms.json", "strategy_room1.json", "strategy_room2.json"):
        shutil.copyfile(f"config/{filename}", config / filename)
    return CatalogStore(config)


def test_catalog_crud_and_entity_correlation(store):
    service = store.put_service(
        {"type": "service", "name": "test_service", "description": "Unit test service"},
        create_only=True,
    )
    assert store.service("test_service")["online_status"] == "online"
    assert service["name"] == "test_service"

    device = store.put_device(
        {
            "type": "device",
            "device_id": "dev1",
            "kind": "test_sensor",
            "room_id": "room1",
            "connector": "test_service",
        },
        create_only=True,
    )
    assert device["room_id"] == "room1"
    with pytest.raises(ValueError, match="correlated devices"):
        store.delete_service("test_service")
    with pytest.raises(ValueError, match="correlated devices"):
        store.delete_room("room1")
    assert store.delete_device("dev1")
    assert store.delete_service("test_service")

    room = store.room("room1")
    room["strategy_version"] = "test_version"
    store.put_room(room)
    assert [item["room_id"] for item in store.list_rooms()] == ["room1", "room2"]


def test_catalog_rejects_broken_correlations(store):
    with pytest.raises(ValueError, match="Unknown connector"):
        store.put_device(
            {
                "type": "device",
                "device_id": "orphan",
                "kind": "sensor",
                "room_id": "room1",
                "connector": "missing_connector",
            }
        )

    strategy = json.loads((store.config_dir / "strategy_room1.json").read_text(encoding="utf-8"))
    strategy["states"]["vault_door_sealed"]["transitions"][0]["prop_id"] = "missing_prop"
    with pytest.raises(ValueError, match="unconfigured props"):
        store.validate_room_strategy(strategy, "room1")

    room = store.room("room1")
    room["dimensions"]["width_m"] = 0
    with pytest.raises(ValueError, match="positive numbers"):
        store.put_room(room)


def test_catalog_persistence_is_valid_json(store):
    store.put_service({"type": "service", "name": "persisted", "description": "Persist me"})
    payload = json.loads(store.catalog_path.read_text(encoding="utf-8"))
    assert any(item["name"] == "persisted" for item in payload["registered_services"])


def test_catalog_http_crud_contract_returns_json(store):
    """Exercise CherryPy's real dispatcher, not only CatalogStore methods."""
    service = SimpleNamespace(
        store=store,
        mqtt=SimpleNamespace(connected=False),
        publish_strategy_update=lambda strategy: None,
    )
    cherrypy.config.update(
        {
            "server.socket_host": "127.0.0.1",
            "server.socket_port": 0,
            "engine.autoreload.on": False,
            "error_page.default": json_error_page,
            "log.screen": False,
        }
    )
    cherrypy.tree.mount(Root(service, store.config_dir), "/")
    cherrypy.engine.start()
    base_url = f"http://127.0.0.1:{cherrypy.server.bound_addr[1]}"
    try:
        response = requests.get(f"{base_url}/rooms", timeout=2)
        assert response.headers["Content-Type"] == "application/json"
        assert [room["room_id"] for room in response.json()["rooms"]] == ["room1", "room2"]

        record = {"type": "service", "name": "http_test", "description": "Created over REST"}
        assert requests.post(f"{base_url}/services", json=record, timeout=2).status_code == 201
        record["description"] = "Updated over REST"
        assert requests.put(f"{base_url}/services?name=http_test", json=record, timeout=2).json()["service"][
            "description"
        ] == "Updated over REST"
        assert requests.delete(f"{base_url}/services?name=http_test", timeout=2).json() == {"deleted": "http_test"}
        missing = requests.get(f"{base_url}/services?name=http_test", timeout=2)
        assert missing.status_code == 404
        assert missing.headers["Content-Type"] == "application/json"
        assert missing.json()["error"]["status"] == 404

        strategy = requests.get(f"{base_url}/config/room1", timeout=2)
        assert strategy.status_code == 200
        assert strategy.json()["room_id"] == "room1"
    finally:
        cherrypy.engine.exit()
        cherrypy.engine.block()
