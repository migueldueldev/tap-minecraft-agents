# Import necessary modules
from mcpi.minecraft import Minecraft
from SharedWorkspace import SharedWorkspace
from Workflow import Workflow
from utils import parse_message, find_agent
import pkgutil
import importlib
import os
import asyncio
from BaseAgent import BaseAgent

def connect_mc() -> Minecraft:
    """Connect to the Minecraft server"""
    try:
        return Minecraft.create()
    except Exception as e:
        print(f"Error connecting to Minecraft: {e}")
        exit(1)

def load_agents(mc, workspace) -> list:
    """Dynamically load agent modules using reflection"""
    agents_dir = os.path.join(os.path.dirname(__file__), "agents")
    for module in pkgutil.iter_modules([agents_dir]):
        importlib.import_module(f"agents.{module.name}")

    instances = []
    for subclass in BaseAgent.__subclasses__():
        obj = subclass(mc, workspace)
        if isinstance(obj, BaseAgent):
            instances.append(obj)

    print(f"Agents loaded: {instances}")
    return instances

async def read_chat_events(mc, workspace, instances, workflow):
    while True:
        chat_events = mc.events.pollChatPosts()
        for event in chat_events:
            print(f"Chat event: {event}")
            await parse_message(event.message, mc, workspace, instances, workflow)
        await asyncio.sleep(0.1)

async def main():
    mc = connect_mc()
    workspace = SharedWorkspace()
    instances = load_agents(mc, workspace)
    workflow = Workflow(mc, workspace, instances)

    agents = ["ExplorerBot", "MinerBot", "BuilderBot"]

    for agent in agents:
        instance = find_agent(instances, agent)
        if instance:
            await instance.start()
        else:
            print(f"{agent} instance not found")
        
    chat_task = asyncio.create_task(read_chat_events(mc, workspace, instances, workflow))
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