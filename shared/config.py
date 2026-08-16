"""Configuration loader utility for reading and parsing JSON configuration files."""

import json
import os
from typing import Dict, Any

def load_config(file_path: str) -> Dict[str, Any]:
    """Load and parse a JSON configuration file from disk.

    Args:
        file_path (str): Path to the JSON configuration file.

    Returns:
        Dict[str, Any]: Parsed JSON data as a dictionary.

    Raises:
        FileNotFoundError: If the specified file_path does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Config file not found: {file_path}")
    with open(file_path, 'r') as f:
        return json.load(f)

