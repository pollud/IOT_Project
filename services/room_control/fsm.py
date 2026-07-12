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
            self._enter_state(self.current_state)
            
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

    def _perform_transition(self, new_state):
        print(f"[{self.room_id}] Transition: {self.current_state} -> {new_state}")
        self.current_state = new_state
        self.scheduler.cancel_all()
        self._enter_state(new_state)
