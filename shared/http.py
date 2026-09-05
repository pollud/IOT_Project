"""Consistent CherryPy server and JSON error configuration."""

from __future__ import annotations

import json
import os
from typing import Any

import cherrypy


def json_error_page(status: str, message: str, traceback: str, version: str) -> str:
    """Return API failures as JSON without exposing server tracebacks."""
    del traceback, version
    try:
        status_code = int(str(status).split()[0])
    except (ValueError, IndexError):
        status_code = 500
    cherrypy.response.headers["Content-Type"] = "application/json"
    return json.dumps(
        {"error": {"status": status_code, "message": message or "Request failed"}},
        separators=(",", ":"),
    )


def server_config(default_port: int) -> dict[str, Any]:
    """Build the common non-reloading HTTP server configuration."""
    return {
        # Containers listen on every container interface; Compose publishes only to localhost.
        "server.socket_host": os.getenv("BIND_HOST", "0.0.0.0"),  # nosec B104
        "server.socket_port": int(os.getenv("PORT", str(default_port))),
        "engine.autoreload.on": False,
        "error_page.default": json_error_page,
    }
