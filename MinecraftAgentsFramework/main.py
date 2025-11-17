# Import necessary modules
from mcpi.minecraft import Minecraft
import mcpi.block as block
import pkgutil
import importlib
import os
from BaseAgent import BaseAgent

# Connect to the Minecraft game
mc = Minecraft.create()

# Interact with the Minecraft world
# mc.postToChat("Hello Minecraft World")
# pos = mc.player.getTilePos()
# mc.setBlock(pos.x + 3, pos.y, pos.z, block.STONE.id)

agents_dir = os.path.join(os.path.dirname(__file__), "agents")
for module in pkgutil.iter_modules([agents_dir]):
    importlib.import_module(f"agents.{module.name}")

instances = []
for subclass in BaseAgent.__subclasses__():
    obj = subclass()
    if isinstance(obj, BaseAgent):
        instances.append(obj)

print(instances)
