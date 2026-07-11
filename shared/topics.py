def build_topic(room: str, device: str, event: str, device_id: str = None) -> str:
    """
    Build an MQTT topic based on the defined architecture.
    Examples:
    - build_topic("roomA", "room", "environment") -> "room/roomA/environment"
    - build_topic("roomA", "badge", "position", "b1") -> "game/roomA/badge/b1/position"
    - build_topic("roomA", "catalog", "config-update") -> "catalog/roomA/config-update"
    - build_topic(None, "system", "alerts") -> "system/alerts"
    - build_topic(None, "command", "emergency") -> "command/emergency"
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
