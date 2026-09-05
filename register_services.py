"""Audit automatic Catalog registration (manual registration is no longer needed)."""

from __future__ import annotations

import os

import requests

CATALOG_URL = os.getenv("CATALOG_URL", "http://localhost:8080").rstrip("/")


def main() -> None:
    services = requests.get(f"{CATALOG_URL}/services", timeout=5).json()["services"]
    devices = requests.get(f"{CATALOG_URL}/devices", timeout=5).json()["devices"]
    rooms = requests.get(f"{CATALOG_URL}/rooms", timeout=5).json()["rooms"]
    print(f"Rooms: {len(rooms)} | Services: {len(services)} | Devices: {len(devices)}")
    for service in sorted(services, key=lambda item: item["name"]):
        print(f"- {service['name']}: {service.get('online_status', 'configured')}")


if __name__ == "__main__":
    main()

