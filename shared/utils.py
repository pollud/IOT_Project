"""Utility helpers for JSON serialization/deserialization and resilience patterns (CircuitBreaker)."""

import json
import time
import dataclasses
from typing import Any

def to_json(obj: Any) -> str:
    """Serialize an object or dataclass instance into a JSON string.

    Args:
        obj (Any): Object or dataclass instance to serialize.

    Returns:
        str: JSON string representation.
    """
    if dataclasses.is_dataclass(obj):
        return json.dumps(dataclasses.asdict(obj))
    return json.dumps(obj)

def from_json(cls: Any, json_str: str) -> Any:
    """Deserialize a JSON string into an instance of class `cls`.

    Args:
        cls (Any): Target dataclass or class type.
        json_str (str): JSON string to parse.

    Returns:
        Any: Instantiated object of class `cls`.
    """
    data = json.loads(json_str)
    return cls(**data)

def compact_json(obj: Any) -> str:
    """Serialize an object or dataclass instance into a compact JSON string without whitespace.

    Args:
        obj (Any): Object or dataclass instance to serialize.

    Returns:
        str: Compact JSON string.
    """
    if dataclasses.is_dataclass(obj):
        return json.dumps(dataclasses.asdict(obj), separators=(',', ':'))
    return json.dumps(obj, separators=(',', ':'))

class CircuitBreakerOpenException(Exception):
    """Exception raised when a call is executed while the CircuitBreaker is in the OPEN state."""
    pass

class CircuitBreaker:
    """Circuit breaker resilience pattern implementation to protect external service calls."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 10.0):
        """Initialize the CircuitBreaker.

        Args:
            failure_threshold (int): Number of consecutive failures before tripping the circuit to OPEN.
            recovery_timeout (float): Time in seconds to wait before transitioning from OPEN to HALF_OPEN.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_state_change = time.time()

    def call(self, func, *args, **kwargs):
        """Execute a function wrapped by the circuit breaker logic.

        Args:
            func (callable): Function to call.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            Any: Return value of func execution.

        Raises:
            CircuitBreakerOpenException: If circuit breaker is currently OPEN.
            Exception: Any exception raised by func.
        """
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_state_change >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                self.last_state_change = now
            else:
                raise CircuitBreakerOpenException("Circuit breaker is OPEN. Fast-failing external call.")

        try:
            result = func(*args, **kwargs)
            if self.state in ("HALF_OPEN", "OPEN"):
                self.state = "CLOSED"
                self.failure_count = 0
                self.last_state_change = now
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_state_change = now
            raise e

