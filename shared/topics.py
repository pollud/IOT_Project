"""MQTT topic generator adhering to system-wide topic conventions."""

def build_topic(room: str, device: str, event: str, device_id: str = None) -> str:
    """Build an MQTT topic string based on target room, device category, event type, and optional device ID.

    Examples:
        - build_topic("roomA", "room", "environment") -> "room/roomA/environment"
        - build_topic("roomA", "badge", "position", "b1") -> "game/roomA/badge/b1/position"
        - build_topic("roomA", "catalog", "config-update") -> "catalog/roomA/config-update"
        - build_topic(None, "system", "alerts") -> "system/alerts"
        - build_topic(None, "command", "emergency") -> "command/emergency"

    Args:
        room (str, optional): Target room identifier (e.g. "roomA").
        device (str): Device or service category ("room", "badge", "prop", "catalog", "system", "command", "session", "analytics", "game").
        event (str): Event or sub-topic name (e.g. "environment", "position", "alerts", "emergency").
        device_id (str, optional): Specific ID of the device (required for "badge" and "prop").

    Returns:
        str: Formatted MQTT topic string.

    Raises:
        ValueError: If device is "badge" or "prop" and device_id is omitted.
    """
    if device == "room":
        if event == "command":
            return f"command/room/{room}"
        return f"room/{room}/{event}"
    elif device in ("badge", "prop"):
        if not device_id:
            raise ValueError("device_id is required for badges and props")
        return f"game/{room}/{device}/{device_id}/{event}"
    elif device == "catalog":
        return f"catalog/{room}/{event}"
    elif device == "system":
        return f"system/{event}"
    elif device == "command" and event == "emergency":
        return "command/emergency"
    elif device == "session":
        return f"session/{room}/{event}"
    elif device == "analytics":
        return f"analytics/{room}/{event}"
    elif device == "game" and event == "status":
        return f"game/{room}/status"
    else:
        return f"custom/{room}/{device}/{event}"

