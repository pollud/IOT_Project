"""Configuration helpers shared by all microservices."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from shared.constants import ROOM_ID_PATTERN


def load_config(file_path: str | Path) -> dict[str, Any]:
    """Load a JSON configuration file and require a JSON object."""
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise TypeError(f"Configuration must contain a JSON object: {path}")
    return data


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    value = int(os.getenv(name, str(default)))
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def env_float(name: str, default: float, minimum: float | None = None) -> float:
    value = float(os.getenv(name, str(default)))
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def env_csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def validate_identifier(value: str, label: str = "identifier") -> str:
    if not re.fullmatch(ROOM_ID_PATTERN, value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value
