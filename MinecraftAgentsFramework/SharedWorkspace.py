import json
import datetime

class SharedWorkspace:
    def __init__(self):
        self.observers = []
        self.log_file = "agent_execution.log"
    
    def register_observer(self, observer):
        if observer not in self.observers:
            self.observers.append(observer)
            
    def remove_observer(self, observer):
        if observer in self.observers:
            self.observers.remove(observer)

    def post_command(self, agent_name, command_data):
        self.log_event("COMMAND_POSTED", agent_name, command_data)
        for observer in self.observers:
            if observer.__class__.__name__ == agent_name:
                observer.receive_command(command_data)
    
    def post_message(self, message):
        self.log_event("MESSAGE_POSTED", message.get('source'), message)
        target = message.get('target')
        for observer in self.observers:
            if observer.__class__.__name__ == target:
                observer.receive_message(message)
    
    def log_event(self, event_type, agent, data):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        log_entry = {
            "timestamp": timestamp,
            "event": event_type,
            "agent": agent,
            "data": data
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def save_final_state(self, agents):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        final_state = {
            "timestamp": timestamp,
            "event": "SYSTEM_SHUTDOWN",
            "agents": [
                {
                    "name": agent.__class__.__name__,
                    "state": agent.get_state().value,
                    "args": agent.args
                }
                for agent in agents
            ]
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(final_state, indent=2) + "\n")