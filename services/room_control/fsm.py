import threading
from scheduler import Scheduler
from actions import ActionExecutor

class RoomFSM:
    def __init__(self, room_id, strategy, mqtt_client):
        self.room_id = room_id
        self.mqtt = mqtt_client
        self.action_executor = ActionExecutor(self.mqtt, room_id)
        self.scheduler = Scheduler(self)
        self.lock = threading.Lock()
        self.load_strategy(strategy)
        
    def load_strategy(self, strategy):
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

    def restore_state(self, state_name):
        with self.lock:
            if state_name in self.states and state_name != self.current_state:
                print(f"[{self.room_id}] Restoring retained FSM state: {state_name}")
                self.current_state = state_name
                self.scheduler.cancel_all()
                self._enter_state(state_name)
            
    def _enter_state(self, state_name):
        print(f"[{self.room_id}] Entering state: {state_name}")
        state_def = self.states.get(state_name, {})
        actions = state_def.get("on_enter", [])
        for act in actions:
            self.action_executor.execute(act)
            
        transitions = state_def.get("transitions", [])
        for t in transitions:
            if t.get("trigger") == "time":
                self.scheduler.schedule(state_name, t.get("duration_seconds", 0), t.get("target_state"))
                
    def event_transition(self, event_type, prop_id, interaction_type, value):
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

    def time_transition(self, from_state, target_state):
        with self.lock:
            if self.current_state == from_state:
                print(f"[{self.room_id}] Time transition {from_state} -> {target_state}")
                self._perform_transition(target_state)

    def force_unlock(self):
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
        with self.lock:
            initial = self.strategy.get("initial_state", "entrance")
            print(f"[{self.room_id}] Resetting Room -> {initial}")
            self._perform_transition(initial)

    def _perform_transition(self, new_state):
        print(f"[{self.room_id}] Transition: {self.current_state} -> {new_state}")
        self.current_state = new_state
        self.scheduler.cancel_all()
        import json
        self.mqtt.publish(f"room/{self.room_id}/status", {"room_id": self.room_id, "current_state": new_state}, retain=True)
        self._enter_state(new_state)
