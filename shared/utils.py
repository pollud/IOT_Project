import json
import dataclasses
from typing import Any

def to_json(obj: Any) -> str:
    if dataclasses.is_dataclass(obj):
        return json.dumps(dataclasses.asdict(obj))
    return json.dumps(obj)

def from_json(cls: Any, json_str: str) -> Any:
    data = json.loads(json_str)
    return cls(**data)

def compact_json(obj: Any) -> str:
    if dataclasses.is_dataclass(obj):
        return json.dumps(dataclasses.asdict(obj), separators=(',', ':'))
    return json.dumps(obj, separators=(',', ':'))

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=10.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_state_change = time.time()

    def call(self, func, *args, **kwargs):
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
