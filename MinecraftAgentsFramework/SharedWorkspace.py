import json
import datetime
from utils import validate_message

class SharedWorkspace:
    # Message types observed by workflow
    WORKFLOW_OBSERVABLE = set({'map.v1', 'materials.requirements.v1', 'inventory.v1', 'build.v1'})
    
    def __init__(self):
        self.observers = []
        self.workflow_observer = None
        self.log_file = "agent_execution.log"
    
    def register_observer(self, observer):
        if observer not in self.observers:
            self.observers.append(observer)
    
    def register_workflow_observer(self, workflow):
        """Register workflow for message observation."""
        self.workflow_observer = workflow
            
    def remove_observer(self, observer):
        if observer in self.observers:
            self.observers.remove(observer)

    def post_command(self, agent_name, command_data):
        self.log_event("COMMAND_POSTED", agent_name, command_data)
        for observer in self.observers:
            if observer.__class__.__name__ == agent_name:
                observer.receive_command(command_data)
    
    def post_message(self, message):
        try:
            validate_message(message)
        except Exception as e:
            print(f"Error: Invalid message format: {e}")
            self.log_event("INVALID_MESSAGE_ERROR", message.get('source', 'SharedWorkspace'), {"error": str(e), "message": message})
            return

        self.log_event("MESSAGE_POSTED", message.get('source'), message)
        target = message.get('target')
        msg_type = message.get('type', '')
        
        # Send to target agent
        for observer in self.observers:
            if observer.__class__.__name__ == target:
                observer.receive_message(message)
        
        # Notify workflow of relevant messages
        if self.workflow_observer and msg_type in self.WORKFLOW_OBSERVABLE:
            self.workflow_observer.receive_message(message)
    
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