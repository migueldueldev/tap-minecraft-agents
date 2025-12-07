from collections import deque
import json
from datetime import datetime

class SharedWorkspace:
    def __init__(self):
        self.command_queues = {}  # {agent_name: deque([commands])}
        self.message_queue = deque()  # mensajes entre bots
        self.log_file = "agent_execution.log"
    
    def post_command(self, agent_name, command_data):
        if agent_name not in self.command_queues:
            self.command_queues[agent_name] = deque()
        self.command_queues[agent_name].append(command_data)
        self.log_event("COMMAND_POSTED", agent_name, command_data)
    
    def get_pending_command(self, agent_name):
        queue = self.command_queues.get(agent_name)
        if queue and len(queue) > 0:
            cmd = queue.popleft()
            self.log_event("COMMAND_CONSUMED", agent_name, cmd)
            return cmd
        return None
    
    def post_message(self, message):
        self.message_queue.append(message)
        self.log_event("MESSAGE_POSTED", message.get('source'), message)
    
    def get_messages_for(self, target):
        messages = [m for m in self.message_queue if m.get('target') == target]
        
        # remover mensajes consumidos
        self.message_queue = deque([m for m in self.message_queue if m.get('target') != target])
        if messages:
            self.log_event("MESSAGES_CONSUMED", target, {"count": len(messages)})
        return messages
    
    def log_event(self, event_type, agent, data):
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "event": event_type,
            "agent": agent,
            "data": data
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def save_final_state(self, agents):
        timestamp = datetime.now().isoformat()
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