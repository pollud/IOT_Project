"""Finite State Machine engine controlling escape room state progression and transitions."""

import threading
from scheduler import Scheduler
from actions import ActionExecutor

class RoomFSM:
    """Thread-safe Finite State Machine managing room state transitions based on prop events and timers."""

    def __init__(self, room_id: str, strategy: dict, mqtt_client):
        """Initialize RoomFSM instance.

        Args:
            room_id (str): Room identifier.
            strategy (dict): Validated strategy configuration dictionary.
            mqtt_client: Instance of MQTTClient.
        """
        self.room_id = room_id
        self.mqtt = mqtt_client
        self.action_executor = ActionExecutor(self.mqtt, room_id)
        self.scheduler = Scheduler(self)
        self.lock = threading.Lock()
        self.load_strategy(strategy)
        
    def load_strategy(self, strategy: dict):
        """Load or reload strategy definition, cancel active timers, publish current status, and enter initial state.

        Args:
            strategy (dict): Room strategy dictionary.
        """
        with self.lock:
            self.strategy = strategy
            self.states = strategy.get("states", {})
            self.current_state = strategy.get("initial_state")
            self.version = strategy.get("version")
            print(f"[{self.room_id}] Loaded strategy version {self.version}")
            self.scheduler.cancel_all()
            
            import json
            self.mqtt.publish(f"room/{self.room_id}/status", {"room_id": self.room_id, "current_state": self.current_state}, retain=True)
            
            self._enter_state(self.current_state)

    def restore_state(self, state_name: str):
        """Restore FSM state from retained status message on reconnect.

        Args:
            state_name (str): Target state name to restore.
        """
        with self.lock:
            if state_name in self.states and state_name != self.current_state:
                print(f"[{self.room_id}] Restoring retained FSM state: {state_name}")
                self.current_state = state_name
                self.scheduler.cancel_all()
                self._enter_state(state_name)
            
    def _enter_state(self, state_name: str):
        """Execute on_enter actions and register time-based transitions for state_name.

        Args:
            state_name (str): Name of state being entered.
        """
        print(f"[{self.room_id}] Entering state: {state_name}")
        state_def = self.states.get(state_name, {})
        actions = state_def.get("on_enter", [])
        for act in actions:
            self.action_executor.execute(act)
            
        transitions = state_def.get("transitions", [])
        for t in transitions:
            if t.get("trigger") == "time":
                self.scheduler.schedule(state_name, t.get("duration_seconds", 0), t.get("target_state"))
                
    def event_transition(self, event_type: str, prop_id: str, interaction_type: str, value: str) -> bool:
        """Evaluate incoming prop event against current state transitions and execute matching transition if found.

        Args:
            event_type (str): Type of event (e.g. "PropEvent").
            prop_id (str): Identifier of prop originating event.
            interaction_type (str): Type of interaction (e.g. "solved", "button_press").
            value (str): Expected event payload value.

        Returns:
            bool: True if transition occurred, False otherwise.
        """
        with self.lock:
            state_def = self.states.get(self.current_state, {})
            transitions = state_def.get("transitions", [])
            for t in transitions:
                if t.get("trigger") == "event":
                    if t.get("event_type") == event_type and \
                       t.get("prop_id") == prop_id and \
                       t.get("interaction_type") == interaction_type and \
                       str(t.get("value")) == str(value):
                        self._perform_transition(t.get("target_state"))
                        return True
            return False

    def time_transition(self, from_state: str, target_state: str):
        """Execute time-triggered state transition if currently in from_state.

        Args:
            from_state (str): State from which timer was started.
            target_state (str): Destination state upon timeout.
        """
        with self.lock:
            if self.current_state == from_state:
                print(f"[{self.room_id}] Time transition {from_state} -> {target_state}")
                self._perform_transition(target_state)

    def force_unlock(self):
        """Force transition room to terminal/cleared state (operator emergency override)."""
        with self.lock:
            terminal_candidates = [
                "game_cleared", "core_unlocked", "mainframes_accessible",
                "escape_pod_ready", "gate_unlocked", "temple_sealed",
                "tomb_opened", "curse_lifted", "patient_escaped",
                "case_solved", "champion_cleared"
            ]
            target_state = None
            for cand in terminal_candidates:
                if cand in self.states:
                    target_state = cand
                    break
            if not target_state:
                state_keys = list(self.states.keys())
                target_state = state_keys[-1] if state_keys else "game_cleared"
                
            print(f"[{self.room_id}] Force Unlocking -> {target_state}")
            self._perform_transition(target_state)

    def reset_room(self):
        """Reset room FSM back to initial entrance state."""
        with self.lock:
            initial = self.strategy.get("initial_state", "entrance")
            print(f"[{self.room_id}] Resetting Room -> {initial}")
            self._perform_transition(initial)

    def _perform_transition(self, new_state: str):
        """Perform transition to new_state, cancel active timers, publish retained status, and enter new state.

        Args:
            new_state (str): Target state name.
        """
        print(f"[{self.room_id}] Transition: {self.current_state} -> {new_state}")
        self.current_state = new_state
        self.scheduler.cancel_all()
        import json
        self.mqtt.publish(f"room/{self.room_id}/status", {"room_id": self.room_id, "current_state": new_state}, retain=True)
        self._enter_state(new_state)

