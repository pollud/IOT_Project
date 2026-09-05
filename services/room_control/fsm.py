"""Recoverable, thread-safe finite state machine for one game room."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from services.room_control.actions import ActionExecutor
from services.room_control.scheduler import Scheduler
from shared.fsm_schema import validate_strategy
from shared.models import GameStatus, SessionEvent, TransitionEvent
from shared.topics import game_status, game_transition, session

LOGGER = logging.getLogger("room_fsm")


class RoomFSM:
    def __init__(
        self,
        room_id: str,
        strategy: dict[str, Any],
        mqtt_client,
        recovered_status: dict[str, Any] | None = None,
        clock=time.time,
    ) -> None:
        validate_strategy(strategy)
        if strategy["room_id"] != room_id:
            raise ValueError("Strategy room_id does not match controller room_id")
        self.room_id = room_id
        self.mqtt = mqtt_client
        self.clock = clock
        self.lock = threading.RLock()
        self.scheduler = Scheduler()
        self.actions = ActionExecutor(mqtt_client, room_id)
        self.strategy = strategy
        self.states = strategy["states"]
        self.version = strategy["version"]
        self._completion_published = False
        self.recovered = self._can_recover(recovered_status)

        now = self.clock()
        if self.recovered:
            status = recovered_status or {}
            self.current_state = str(status["current_state"])
            self.session_id = str(status["session_id"])
            self.started_at = float(status["started_at"])
            self.state_entered_at = float(status.get("state_entered_at", now))
            self.completed = bool(status.get("completed", False))
            self._completion_published = self.completed
        else:
            self.current_state = strategy["initial_state"]
            self.session_id = self._new_session_id()
            self.started_at = now
            self.state_entered_at = now
            self.completed = False

    def _can_recover(self, status: dict[str, Any] | None) -> bool:
        return bool(
            status
            and status.get("strategy_version") == self.version
            and status.get("current_state") in self.states
            and status.get("session_id")
            and status.get("started_at")
        )

    def _new_session_id(self) -> str:
        return f"{self.room_id}-{uuid.uuid4().hex[:12]}"

    def start(self) -> None:
        with self.lock:
            if self.recovered:
                LOGGER.info("[%s] recovered session %s in state %s", self.room_id, self.session_id, self.current_state)
                self._schedule_timed_transitions(recovery=True)
                self.publish_status()
                return
            self._publish_session("started")
            self._enter_state(self.current_state, execute_actions=True)

    def close(self) -> None:
        self.scheduler.cancel_all()

    def _publish_session(self, event: str) -> None:
        now = self.clock()
        payload = SessionEvent(
            room_id=self.room_id,
            session_id=self.session_id,
            timestamp=now,
            duration_seconds=(now - self.started_at) if event == "ended" else None,
            success=self.completed if event == "ended" else None,
        )
        self.mqtt.publish(session(self.room_id, event), payload, qos=1)

    def publish_status(self) -> None:
        now = self.clock()
        payload = GameStatus(
            room_id=self.room_id,
            session_id=self.session_id,
            current_state=self.current_state,
            strategy_version=self.version,
            started_at=self.started_at,
            state_entered_at=self.state_entered_at,
            updated_at=now,
            completed=self.completed,
        )
        self.mqtt.publish(game_status(self.room_id), payload, qos=1, retain=True)

    def _schedule_timed_transitions(self, recovery: bool = False) -> None:
        definition = self.states[self.current_state]
        for index, transition in enumerate(definition["transitions"]):
            if transition["trigger"] != "time":
                continue
            duration = float(transition["duration_seconds"])
            if recovery:
                duration = max(0.05, duration - max(0.0, self.clock() - self.state_entered_at))
            from_state = self.current_state
            target_state = transition["target_state"]
            self.scheduler.schedule(
                f"{from_state}:{index}",
                duration,
                lambda source=from_state, target=target_state: self.time_transition(source, target),
            )

    def _enter_state(self, state_name: str, execute_actions: bool) -> None:
        LOGGER.info("[%s] entering %s", self.room_id, state_name)
        if execute_actions:
            for action in self.states[state_name]["on_enter"]:
                self.actions.execute(action)
        terminal = bool(self.states[state_name].get("is_terminal"))
        if terminal and not self._completion_published:
            self.completed = True
            self._completion_published = True
            self.publish_status()
            self._publish_session("ended")
            return
        self.publish_status()
        self._schedule_timed_transitions()

    def _perform_transition(self, target_state: str, trigger: str, trigger_id: str | None) -> None:
        previous = self.current_state
        now = self.clock()
        elapsed = max(0.0, now - self.state_entered_at)
        self.scheduler.cancel_all()
        self.current_state = target_state
        self.state_entered_at = now
        transition = TransitionEvent(
            room_id=self.room_id,
            session_id=self.session_id,
            from_state=previous,
            to_state=target_state,
            trigger=trigger,
            trigger_id=trigger_id,
            elapsed_seconds=elapsed,
            timestamp=now,
        )
        self.mqtt.publish(game_transition(self.room_id), transition, qos=1)
        self._enter_state(target_state, execute_actions=True)

    def event_transition(self, prop_id: str, interaction_type: str, value: str) -> bool:
        with self.lock:
            if self.completed:
                return False
            for transition in self.states[self.current_state]["transitions"]:
                if (
                    transition["trigger"] == "event"
                    and transition["event_type"] == "PropEvent"
                    and transition["prop_id"] == prop_id
                    and transition["interaction_type"] == interaction_type
                    and str(transition["value"]) == str(value)
                ):
                    self._perform_transition(transition["target_state"], "event", prop_id)
                    return True
            return False

    def time_transition(self, from_state: str, target_state: str) -> bool:
        with self.lock:
            if self.completed or self.current_state != from_state:
                return False
            self._perform_transition(target_state, "time", None)
            return True

    def reset_room(self) -> None:
        with self.lock:
            self.scheduler.cancel_all()
            now = self.clock()
            self.current_state = self.strategy["initial_state"]
            self.session_id = self._new_session_id()
            self.started_at = now
            self.state_entered_at = now
            self.completed = False
            self._completion_published = False
            self.recovered = False
            self._publish_session("started")
            self._enter_state(self.current_state, execute_actions=True)

    def force_unlock(self) -> None:
        with self.lock:
            self.actions.execute({"action": "unlockDoor", "target": "main_door"})

    def load_strategy(self, strategy: dict[str, Any]) -> None:
        validate_strategy(strategy)
        if strategy["room_id"] != self.room_id:
            raise ValueError("Cannot load a strategy for another room")
        with self.lock:
            self.scheduler.cancel_all()
            self.strategy = strategy
            self.states = strategy["states"]
            self.version = strategy["version"]
            if self.current_state not in self.states:
                self.reset_room()
                return
            self._schedule_timed_transitions(recovery=True)
            self.publish_status()
