# Import necessary modules
from mcpi.minecraft import Minecraft
from SharedWorkspace import SharedWorkspace
import mcpi.block as block
import pkgutil
import importlib
import os
import asyncio
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
    if len(components) >= 2:
        agent = components[0]
        action = components[1]
        parameters = components[2:]

        if agent == "agent":
            if action in ["help", "status", "stop", "pause", "resume"]:
                if action == "help":
                    output = ["Available commands:", "agent help", "agent status", "agent stop", "agent pause", "agent resume"]
                    for msg in output:
                        mc.postToChat(msg)
                elif action == "status":
                    pass
                elif action == "stop":
                    pass
                elif action == "pause":
                    pass
                elif action == "resume":
                    pass
            else: mc.postToChat(f'Action "{action}" in command "{message}" is not recognized')
        elif agent == "explorer":
            if action in ["start", "stop", "set", "status"]:
                if action == "start":
                    if len(parameters) >= 2:
                        try:
                            x = parameters[0].split("=")
                            if (len(x) == 2 and x[0] == "x"):
                                x = int(x[1])
                            else: return mc.postToChat(f'Invalid parameter format in command "{message}"')

                            z = parameters[1].split("=")
                            if (len(z) == 2 and z[0] == "z"):
                                z = int(z[1])
                            else: return mc.postToChat(f'Invalid parameter format in command "{message}"')
                            
                            range = 32
                            if (len(parameters) == 3):
                                range = parameters[2].split("=")
                                if (len(range) == 2 and range[0] == "range"):
                                    range = int(range[1])
                                else: return mc.postToChat(f'Invalid parameter format in command "{message}"')

                            # start here
                            workspace.post_command("ExplorerBot", {
                                "action": "start",
                                "x": x,
                                "z": z,
                                "range": range
                            })
                            mc.postToChat("Command queued for ExplorerBot")
                        except ValueError:
                            mc.postToChat(f'Invalid parameter format in command "{message}"')
                    else: mc.postToChat(f'Insufficient parameters in command "{message}"')
                elif action == "stop":
                    workspace.post_command("ExplorerBot", {
                        "action": "stop"
                    })
                    mc.postToChat("Command queued for ExplorerBot")
                elif action == "set":
                    if len(parameters) == 2:
                        if parameters[0] == "range":
                            try:
                                range = int(parameters[1])

                                workspace.post_command("ExplorerBot", {
                                "action": "set",
                                "range": range
                                })
                                mc.postToChat(f'Command queued for ExplorerBot')
                            except ValueError:
                                mc.postToChat(f'Invalid number format in command "{message}"')
                        else: mc.postToChat(f'Invalid parameter format in command "{message}"')
                    else: mc.postToChat(f'Insufficient parameters in command "{message}"')
                elif action == "status":
                    explorer_agent = await find_explorer_bot()
                    if explorer_agent:
                        state = explorer_agent.get_state()
                        mc.postToChat(f'Explorer agent status: {state.value}')
                    else: mc.postToChat("Explorer agent not found")
            else: mc.postToChat(f'Action "{action}" in command "{message}" is not recognized')
        elif agent == "miner":
            if action in ["start", "set", "fulfill", "pause", "resume", "status"]:
                pass
            else: mc.postToChat(f'Action "{action}" in command "{message}" is not recognized')
        elif agent == "builder":
            if action in ["plan", "bom", "build", "pause", "resume"]:
                    if action == "plan":
                        if len(parameters) >= 2:
                            try:
                                x = parameters[0].split("=")
                                if (len(x) == 2 and x[0] == "x"):
                                    x = int(x[1])
                                else: return mc.postToChat(f'Invalid parameter format in command "{message}"')

                                z = parameters[1].split("=")
                                if (len(z) == 2 and z[0] == "z"):
                                    z = int(z[1])
                                else: return mc.postToChat(f'Invalid parameter format in command "{message}"')
                                # list plan here
                            except ValueError:
                                mc.postToChat(f'Invalid parameter format in command "{message}"')
                        else: mc.postToChat(f'Insufficient parameters in command "{message}"')
                    elif action == "bom":
                        pass
                    elif action == "build":
                        pass
                    elif action == "pause":
                        pass
                    elif action == "resume":
                        pass
            else: mc.postToChat(f'Action "{action}" in command "{message}" is not recognized')
        elif agent == "workflow":
            if action == "run":
                pass
            else: mc.postToChat(f'Action "{action}" in command "{message}" is not recognized')
        else:
            print("Message is not a command")
    else:
        print("Message is not a command")

def find_explorer_bot():
    for instance in instances:
        if instance.__class__.__name__ == "ExplorerBot":
            return instance
    return None

async def read_chat_events():
    while True:
        chat_events = mc.events.pollChatPosts()
        for event in chat_events:
            print(f"Chat event: {event}")
            await parse_message(event.message)
        await asyncio.sleep(1)

async def main():
    explorer_agent = find_explorer_bot()
    if explorer_agent:
        await explorer_agent.start()
    else:
        print("ExplorerBot instance not found")
        
    asyncio.create_task(read_chat_events())
    print("Ready")

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())