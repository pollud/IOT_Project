from pathlib import Path

import yaml


def test_compose_contract_is_complete_private_and_non_root():
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert len(services) == 16  # broker + 15 application containers
    assert {
        "mosquitto",
        "catalog",
        "environment_room1",
        "environment_room2",
        "room_actuator_room1",
        "room_actuator_room2",
        "badge_room1",
        "badge_room2",
        "prop_room1",
        "prop_room2",
        "room_control_room1",
        "room_control_room2",
        "safety_monitor",
        "timeseries_adapter",
        "analytics",
        "web_dashboard",
    } == set(services)

    for name, definition in services.items():
        for dependency in definition.get("depends_on", {}):
            assert dependency in services, (name, dependency)
        for port in definition.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)
        if "build" not in definition:
            continue
        dockerfile = root / definition["build"]["dockerfile"]
        assert dockerfile.is_file(), dockerfile
        assert "USER 65532:65532" in dockerfile.read_text(encoding="utf-8"), name

    assert services["catalog"]["volumes"] == ["catalog_config:/app/config"]
    assert services["timeseries_adapter"]["volumes"] == ["timeseries_data:/var/lib/timeseries"]
    assert "volumes" not in services["analytics"]  # no shared-file data exchange
    assert services["safety_monitor"]["environment"]["MAX_CO2_PPM"] == "${MAX_CO2_PPM:-1500}"
    assert services["timeseries_adapter"]["environment"]["RETENTION_DAYS"] == "${RETENTION_DAYS:-30}"
    assert set(compose["volumes"]) == {"catalog_config", "mosquitto_data", "timeseries_data"}
