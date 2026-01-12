# Import necessary modules
from logging_config import setup_logging, get_logger
from utils import find_agent, parse_message
from mcpi.minecraft import Minecraft
from base_agent import BaseAgent
from shared_workspace import SharedWorkspace
from workflow import Workflow
import pkgutil
import importlib
import os
import asyncio

# Initialize logging
logger = setup_logging("DEBUG")

def connect_mc() -> Minecraft:
    """Connect to the Minecraft server"""
    try:
        logger.info("Connecting to Minecraft server...")
        mc = Minecraft.create()
        logger.info("Successfully connected to Minecraft server")
        return mc
    except Exception as e:
        logger.error("Error connecting to Minecraft: %s", e)
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

    logger.info("Agents loaded: %s", instances)
    return instances

async def read_chat_events(mc, workspace, instances, workflow):
    """Continuously poll and process chat events from the Minecraft server."""
    while True:
        chat_events = mc.events.pollChatPosts()
        for event in chat_events:
            logger.debug("Chat event: %s", event)
            await parse_message(event.message, mc, workspace, instances, workflow)
        await asyncio.sleep(0.1)

async def main():
    """Initialize the Minecraft Agents Framework and start the main event loop."""
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
            logger.warning("%s instance not found", agent)

    chat_task = asyncio.create_task(read_chat_events(mc, workspace, instances, workflow))
    logger.info("Minecraft Agents Framework is ready")

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
        logger.info("Program interrupted by user")