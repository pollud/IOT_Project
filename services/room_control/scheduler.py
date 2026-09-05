"""Thread-safe timer scheduler for FSM time transitions."""

from __future__ import annotations

import threading
from collections.abc import Callable


class Scheduler:
    def __init__(self) -> None:
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.RLock()

    def schedule(self, key: str, duration: float, callback: Callable[[], None]) -> None:
        if duration <= 0:
            raise ValueError("Timer duration must be positive")
        with self._lock:
            previous = self._timers.pop(key, None)
            if previous:
                previous.cancel()
            timer = threading.Timer(duration, self._run, args=(key, callback))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def _run(self, key: str, callback: Callable[[], None]) -> None:
        with self._lock:
            self._timers.pop(key, None)
        callback()

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

