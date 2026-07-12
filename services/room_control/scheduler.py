import threading

class Scheduler:
    def __init__(self, fsm):
        self.fsm = fsm
        self.timers = {}
        self.lock = threading.Lock()
        
    def schedule(self, state_name, duration, target_state):
        with self.lock:
            if state_name in self.timers:
                self.timers[state_name].cancel()
                
            def on_timeout():
                self.fsm.time_transition(state_name, target_state)
                
            t = threading.Timer(duration, on_timeout)
            self.timers[state_name] = t
            t.start()
            
    def cancel_all(self):
        with self.lock:
            for t in self.timers.values():
                t.cancel()
            self.timers.clear()
