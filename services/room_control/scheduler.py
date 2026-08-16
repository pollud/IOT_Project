"""State transition timer scheduler for timed FSM transitions."""

import threading

class Scheduler:
    """Manages thread-safe timers for executing automatic time-based state transitions in RoomFSM."""

    def __init__(self, fsm):
        """Initialize Scheduler instance.

        Args:
            fsm: Reference to the parent RoomFSM instance.
        """
        self.fsm = fsm
        self.timers = {}
        self.lock = threading.Lock()
        
    def schedule(self, state_name: str, duration: float, target_state: str):
        """Schedule a timer to trigger a state transition from state_name to target_state after duration seconds.

        Args:
            state_name (str): Current source state name.
            duration (float): Delay in seconds before triggering transition.
            target_state (str): Target state name upon timer expiration.
        """
        with self.lock:
            if state_name in self.timers:
                self.timers[state_name].cancel()
                
            def on_timeout():
                self.fsm.time_transition(state_name, target_state)
                
            t = threading.Timer(duration, on_timeout)
            self.timers[state_name] = t
            t.start()
            
    def cancel_all(self):
        """Cancel and clear all active scheduled state transition timers."""
        with self.lock:
            for t in self.timers.values():
                t.cancel()
            self.timers.clear()

