from jsonschema import validate
import datetime
import uuid
import asyncio

MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "source": {"type": "string"},
        "target": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"},
        "payload": {"type": "object"},
        "status": {"type": "string", "enum": ["SUCCESS", "PENDING", "FAILED", "COMPLETED", "IN_PROGRESS"]},
        "context": {
            "type": "object",
            "properties": {
                "task_id": {"type": ["string", "null"]},
                "state": {"type": "string"}
            }
        }
    },
    "required": ["type", "source", "target", "timestamp", "payload", "status"]
}

def create_message(msg_type, source, target, payload, status="SUCCESS", context=None):
    """
    Creates a standardized JSON inter-agent communication message
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
    message = {
        "id": str(uuid.uuid4()),
        "type": msg_type,
        "source": source,
        "target": target,
        "timestamp": timestamp,
        "payload": payload,
        "status": status
    }
    if context:
        message["context"] = context
    
    # Validate immediately on creation
    try:
        validate_message(message)
    except Exception as e:
        print(f"Warning: Created message does not match schema: {e}")
        
    return message

def create_command(source, target, action, parameters, context=None):
    """
    Creates a standardized JSON command message
    """
    payload = {
        "action": action,
        "parameters": parameters
    }
    return create_message("command.control.v1", source, target, payload, status="SUCCESS", context=context)

def validate_message(message):
    """
    Validates the structure and integrity of a message using JSON Schema.
    Returns True if valid, raises an exception otherwise.
    """
    validate(instance=message, schema=MESSAGE_SCHEMA)
    return True

def parse_parameters(raw_parameters):
    """
    Parse in-game chat command parameters into a dictionary.
    Supports "key=value" pairs and "key value" pairs.
    """
    parameters = {}
    i = 0
    while i < len(raw_parameters):
        param = raw_parameters[i]
        
        if '=' in param:
            key, value = param.split('=', 1)
            try:
                parameters[key] = int(value)
            except ValueError:
                try:
                    parameters[key] = float(value)
                except ValueError:
                    parameters[key] = value
            i += 1
        elif i + 1 < len(raw_parameters) and '=' not in raw_parameters[i + 1]:
            key = param
            value = raw_parameters[i + 1]
            try:
                parameters[key] = int(value)
            except ValueError:
                try:
                    parameters[key] = float(value)
                except ValueError:
                    parameters[key] = value
            i += 2  
        else:
            parameters[param] = None
            i += 1
    
    return parameters

def find_agent(instances, agent_class_name):
    """Find an agent instance by its class name."""
    for instance in instances:
        if instance.__class__.__name__ == agent_class_name:
            return instance
    return None

async def handle_workflow_command(action: str, parameters: list, workflow, mc, workspace, instances):
    """Handle workflow commands separately from agent commands."""
    valid_actions = ["run", "stop", "help"]
    if action not in valid_actions:
        mc.postToChat(f'Action "{action}" not valid for workflow execution')
        return
    
    parsed_params = parse_parameters(parameters)
    
    if action == "run":
        asyncio.create_task(workflow.run(parsed_params))
    elif action == "stop":
        workflow.stop()
    elif action == "help":
        workflow.help()

async def parse_message(message, mc, workspace, instances, workflow):
    """
    Parse chat messages and send commands to appropriate agents or workflow.
    Expected format: ./[agent] [action] [parameters...]
    """
    components = message.split(" ")
    if components and components[0].startswith("./") and len(components) >= 2:
        agent = components[0][2:]
        action = components[1]
        parameters = components[2:]
    
        agent_map = {
            "explorer": "ExplorerBot",
            "miner": "MinerBot",
            "builder": "BuilderBot",
        }

        # Handle workflow command separately
        if agent == "workflow":
            await handle_workflow_command(action, parameters, workflow, mc, workspace, instances)
            return
        
        if agent not in agent_map:
            mc.postToChat(f'Agent "{agent}" not recognized')
            return
        
        agent_class_name = agent_map[agent]
        agent_instance = find_agent(instances, agent_class_name)
        
        if not agent_instance:
            mc.postToChat(f'Agent instance "{agent_class_name}" not found')
            return
        
        valid_action = {
            "explorer" : ["start", "set", "stop", "status", "pause", "resume", "help", "toggle", "confirm", "queue"],
            "miner" : ["start", "set", "fulfill", "pause", "resume", "status", "stop", "help", "test"],
            "builder" : ["plan", "bom", "build", "pause", "resume", "stop", "status", "help"],
        }

        if action not in valid_action.get(agent, []):
            mc.postToChat(f'Action "{action}" not valid for agent "{agent}"')
            return
        
        context = {
            "task_id": str(id(asyncio.current_task()))
        }
        command = create_command("User", agent_class_name, action, parse_parameters(parameters), context)

        workspace.post_command(agent_class_name, command)
        print(f'Command "{action} {parameters}" sent to agent "{agent}"')
