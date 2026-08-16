"""Loader module for reading and validating room FSM strategy configurations from disk or catalog REST service."""

import json
import time
import requests
from shared.fsm_schema import validate_strategy

def load_strategy_from_file(filepath: str) -> dict:
    """Load and validate a room FSM strategy JSON configuration file from disk.

    Includes retry logic to handle file lock or partial write races during config updates.

    Args:
        filepath (str): Absolute or relative path to the strategy JSON file.

    Returns:
        dict: Parsed and validated strategy dictionary.

    Raises:
        json.JSONDecodeError: If JSON decoding fails on all retry attempts.
        jsonschema.exceptions.ValidationError: If strategy schema validation fails.
    """
    for i in range(5):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            validate_strategy(data)
            return data
        except json.JSONDecodeError as e:
            if i == 4:
                raise e
            time.sleep(0.1)

def load_strategy_from_catalog(room_id: str) -> dict:
    """Fetch and validate room strategy configuration from the Catalog service REST API.

    Args:
        room_id (str): Room identifier string.

    Returns:
        dict or None: Strategy dictionary if fetched and validated successfully, else None.
    """
    try:
        r = requests.get(f"http://catalog:8080/config/{room_id}")
        if r.status_code == 200:
            data = r.json()
            validate_strategy(data)
            return data
    except Exception as e:
        print(f"Error loading from catalog: {e}")
    return None

