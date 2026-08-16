"""Global system-wide constants for MQTT communication and networking."""

# Default MQTT broker connection parameters
DEFAULT_BROKER: str = "localhost"
DEFAULT_PORT: int = 1883

# MQTT Quality of Service (QoS) levels
QOS_AT_MOST_ONCE: int = 0
QOS_AT_LEAST_ONCE: int = 1
QOS_EXACTLY_ONCE: int = 2

