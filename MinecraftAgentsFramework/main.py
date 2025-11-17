# Import necessary modules
from mcpi.minecraft import Minecraft
import mcpi.block as block

# Connect to the Minecraft game
mc = Minecraft.create()

# Interact with the Minecraft world
mc.postToChat("Hello Minecraft World")
pos = mc.player.getTilePos()
mc.setBlock ( pos.x +3 , pos.y , pos.z , block.STONE.id)