# Import necessary modules
from mcpi.minecraft import Minecraft
from SharedWorkspace import SharedWorkspace
import pkgutil
import importlib
import os
import asyncio
import datetime
from BaseAgent import BaseAgent

# Connect to the Minecraft game
mc = Minecraft.create()
workspace = SharedWorkspace()

agents_dir = os.path.join(os.path.dirname(__file__), "agents")
for module in pkgutil.iter_modules([agents_dir]):
    importlib.import_module(f"agents.{module.name}")

instances = []
for subclass in BaseAgent.__subclasses__():
    obj = subclass(mc, workspace)
    if isinstance(obj, BaseAgent):
        instances.append(obj)

print(instances)

async def parse_message(message):
    components = message.split(" ")
    if components and components[0].startswith("./") and len(components) >= 2:
        agent = components[0][2:]
        action = components[1]
        parameters = components[2:]
    
        agent_map = {
            "explorer": "ExplorerBot",
            "miner": "MinerBot",
            "builder": "BuilderBot",
            "workflow": "Workflow"
        }

        if agent not in agent_map:
            mc.postToChat(f'Agent "{agent}" not recognized')
            return
        
        agent_class_name = agent_map[agent]
        agent_instance = find_agent(agent_class_name)
        
        if not agent_instance:
            mc.postToChat(f'Agent instance "{agent_class_name}" not found')
            return
        
        valid_action = {
            "explorer" : ["start", "set", "stop", "status", "pause", "resume", "help", "toggle", "confirm", "queue"],
            "miner" : ["start", "set", "fulfill", "pause", "resume", "status", "stop", "help", "test"],
            "builder" : ["plan", "bom", "build", "pause", "resume", "stop", "status", "help"],
            "workflow" : "run"
        }

        if action not in valid_action.get(agent, []):
            mc.postToChat(f'Action "{action}" not valid for agent "{agent}"')
            return
        
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        
        command = {
            "type": "command.control.v1",
            "source": "User",
            "target": agent_class_name,
            "timestamp": timestamp,
            "payload": {
                "action": action,
                "parameters": parse_parameters(parameters)
            },
            "status": "SUCCESS",
            "context": {
                "task_id": str(id(asyncio.current_task()))
            }
        }

        workspace.post_command(agent_class_name, command)
        print(f'Command "{action} {parameters}" sent to agent "{agent}"')

def parse_parameters(raw_parameters):
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

def find_agent(agent_class_name):
    for instance in instances:
        if instance.__class__.__name__ == agent_class_name:
            return instance
    return None

async def read_chat_events():
    while True:
        chat_events = mc.events.pollChatPosts()
        for event in chat_events:
            print(f"Chat event: {event}")
            await parse_message(event.message)
        await asyncio.sleep(0.1)

async def main():
    explorer_agent = find_agent("ExplorerBot")
    if explorer_agent:
        await explorer_agent.start()
    else:
        print("ExplorerBot instance not found")
    
    miner_agent = find_agent("MinerBot")
    if miner_agent:
        await miner_agent.start()
    else:
        print("MinerBot instance not found")
        
    chat_task = asyncio.create_task(read_chat_events())
    print("Ready")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        for instance in instances:
            instance.stop()

        chat_task.cancel()
        pending = asyncio.all_tasks() - {asyncio.current_task()}
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        workspace.save_final_state(instances)

if __name__ == "__main__":
    try: 
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")