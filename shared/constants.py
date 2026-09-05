"""System-wide networking, QoS and validation constants."""

DEFAULT_BROKER = "mosquitto"
DEFAULT_MQTT_PORT = 1883
DEFAULT_CATALOG_URL = "http://catalog:8080"
DEFAULT_TIMESERIES_URL = "http://timeseries_adapter:8085"
DEFAULT_ANALYTICS_URL = "http://analytics:8086"

ROOM_ID_PATTERN = r"^[a-z][a-z0-9_-]{1,31}$"
