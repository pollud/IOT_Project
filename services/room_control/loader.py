"""Validated strategy retrieval from the Game Catalog REST interface."""

from __future__ import annotations

from shared.catalog_client import CatalogClient
from shared.fsm_schema import validate_strategy


def load_strategy_from_catalog(catalog: CatalogClient, room_id: str) -> dict:
    strategy = catalog.strategy(room_id)
    validate_strategy(strategy)
    if strategy["room_id"] != room_id:
        raise ValueError("Catalog returned a strategy for another room")
    return strategy

