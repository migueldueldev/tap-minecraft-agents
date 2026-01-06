from BaseAgent import BaseAgent, AgentState
from mcpi.minecraft import Minecraft
from functools import reduce
import mcpi.block as block
import datetime
import asyncio
from agents.MiningStrategy import MiningStrategy, VerticalSearchStrategy, GridSearchStrategy, VeinSearchStrategy

# Materials that are provided automatically and do not need to be mined
AUTO_PROVIDED_MATERIALS = [
    "GRASS", "DIRT", "GRAVEL", "SAND", "WOOD_PLANKS", "WOOD", "SANDSTONE", "WOOL",
    "LEAVES", "GLASS", "BRICK_BLOCK", "BOOKSHELF", "MOSS_STONE", "TORCH",
    "STAIRS_WOOD", "CHEST", "DOOR_WOOD", "LADDER", "STAIRS_COBBLESTONE",
    "FENCE", "GLOWSTONE_BLOCK", "STONE_BRICK", "GLASS_PANE", "FENCE_GATE",
    "SAPLING", "BED", "COBWEB", "GRASS_TALL", "FLOWER_YELLOW", "FLOWER_CYAN",
    "MUSHROOM_BROWN", "MUSHROOM_RED", "STONE_SLAB_DOUBLE", "STONE_SLAB",
    "TNT", "FIRE", "CRAFTING_TABLE", "FARMLAND", "FURNACE_INACTIVE",
    "FURNACE_ACTIVE", "DOOR_IRON", "SNOW", "ICE", "SNOW_BLOCK", "CACTUS",
    "CLAY", "SUGAR_CANE", "MELON", "BEDROCK_INVISIBLE", "GLOWING_OBSIDIAN",
    "NETHER_REACTOR_CORE", "OBSIDIAN", "BEDROCK", "WATER", "WATER_STATIONARY",
    "LAVA", "LAVA_STATIONARY", "COBBLESTONE"
]

# Materials that can be mined (ores and stone based blocks)
MINABLE_MATERIALS = [
    "STONE", "COAL_ORE", "IRON_ORE", "GOLD_ORE",
    "DIAMOND_ORE", "REDSTONE_ORE", "LAPIS_LAZULI_ORE"
]

# Materials that require processing from raw ores
PROCESSABLE_MATERIALS = {
    "IRON_BLOCK": {"raw": "IRON_ORE", "amount": 9, "process": "smelt"},
    "GOLD_BLOCK": {"raw": "GOLD_ORE", "amount": 9, "process": "smelt"},
    "DIAMOND_BLOCK": {"raw": "DIAMOND_ORE", "amount": 9, "process": "craft"},
    "LAPIS_LAZULI_BLOCK": {"raw": "LAPIS_LAZULI_ORE", "amount": 9, "process": "craft"},
    "DOOR_IRON": {"raw": "IRON_ORE", "amount": 6, "process": "smelt"}
}

class MinerBot(BaseAgent):
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.mc = mc
        self.workspace = workspace
        self.mining_strategy_name = ""
        self.mining_strategy: MiningStrategy = None
        self.material_requirements = {}
        self.inventory = {}
        self.coords = {}
        self.current_position = {}
        self.current_bom = None
        self.mining_position = None
        self.is_mining = False
        self.ready_to_mine = False
        self.mining_event = asyncio.Event()
        self.blocks = self.get_block_names()
        self.strategy_map = {
            "vertical": VerticalSearchStrategy,
            "grid": GridSearchStrategy,
            "vein": VeinSearchStrategy
        }

    async def perceive(self, **kwargs):
        messages = self.get_messages()
        
        for message in messages:
            message_type = message.get("type")
            
            if message_type == "materials.requirements.v1":
                self.handle_material_requirements(message)

        pos = self.mc.player.getTilePos()
        self.x = kwargs.get("x", pos.x)
        self.z = kwargs.get("z", pos.z)
        self.y = kwargs.get("y", pos.y)
        
        self.kwargs_strategy = kwargs.get("strategy", self.mining_strategy_name)
        if self.kwargs_strategy:
            self.mining_strategy_name = self.kwargs_strategy

        self.coords = {"x": self.x, "y": self.y, "z": self.z, "strategy": self.mining_strategy_name}
        
        return self.coords

    async def decide(self, **kwargs):
        target_class = self.strategy_map.get(self.mining_strategy_name.lower(), VerticalSearchStrategy)
        
        if self.current_bom:
            if self.mining_strategy is None or not isinstance(self.mining_strategy, target_class):
                print(f"MinerBot: Switching strategy to {target_class.__name__} (requested: {self.mining_strategy_name})")
                self.mining_strategy = target_class(self.mc, self.__class__.__name__, self.workspace, agent=self)
                
                self.workspace.log_event(
                    "STRATEGY_SELECTED",
                    self.__class__.__name__,
                    {
                        "strategy": self.mining_strategy.get_strategy_name(),
                        "requirements": self.material_requirements,
                    }
                )
            
            if self.ready_to_mine and self.state != AgentState.RUNNING:
                self.set_state(AgentState.RUNNING, "Mining in progress")
        elif self.state == AgentState.RUNNING:
            self.set_state(AgentState.IDLE, "No active mining task")

    async def act(self, **kwargs):
        if not self.current_bom or not self.mining_strategy or not self.ready_to_mine:
            await asyncio.sleep(0.5)
            return
        
        if self.requirements_fulfilled():
            self.send_inventory_update(complete=True)
            self.mc.postToChat(f"MinerBot: All requirements fulfilled!")
            self.current_bom = None
            self.is_mining = False
            self.ready_to_mine = False
            self.mining_position = None
            self.current_position.clear()
            self.material_requirements.clear()
            self.inventory.clear()
            return
        
        if not self.mining_position:
            pos = self.mc.player.getTilePos()
            self.mining_position = (pos.x, self.y, pos.z)
        
        if not self.is_mining:
            self.is_mining = True
            collected = {}
            try:
                if self.current_position:
                    self.mc.postToChat(f"MinerBot: Resuming mining from offset {self.current_position.get('x', 0)}, {self.current_position.get('y', 0)}, {self.current_position.get('z', 0)} with strategy {self.mining_strategy.get_strategy_name()}")
                else: 
                    self.mc.postToChat(f"MinerBot: Starting mining at {self.mining_position} with strategy {self.mining_strategy.get_strategy_name()}") 
                
                mining_task = asyncio.create_task(
                    self.mining_strategy.mine(
                        self.get_minable_requirements(), 
                        self.mining_position,
                        self.current_position,
                        self.coords
                    )   
                )  
                
                mining_event_task = asyncio.create_task(self.mining_event.wait())
                interrupt_event_task = asyncio.create_task(self.interrupt_event.wait())
                done, pending = await asyncio.wait(
                    {mining_task, mining_event_task, interrupt_event_task},
                    return_when=asyncio.FIRST_COMPLETED
                )

                if mining_task not in done:
                    mining_task.cancel()
                    try:
                        await mining_task
                    except asyncio.CancelledError:
                        pass
                
                if mining_event_task in done:
                    self.mc.postToChat("MinerBot: Mining interrupted")
                    self.mining_event.clear()
                    self.is_mining = False
                    self.mining_position = None
                    self.ready_to_mine = False 
                    self.current_position.clear()
                elif interrupt_event_task in done:
                    if self.should_stop:
                        self.mc.postToChat("MinerBot: Mining interrupted due to stop command")
                        self.is_mining = False
                        self.mining_position = None
                        self.ready_to_mine = False
                        self.current_position.clear()
                    else:
                        self.mc.postToChat("MinerBot: Mining interrupted due to pause command")
                        self.is_mining = False
                    self.interrupt_event.clear()
                else:
                    collected = mining_task.result()
                    self.is_mining = False
                    
                if collected:
                    for material, quantity in collected.items():
                        if material not in self.inventory:
                            self.inventory[material] = 0
                        self.inventory[material] += quantity
                    self.convert_ores_to_blocks()
                
                self.send_inventory_update(complete=False)
                
                if not self.requirements_fulfilled() and not self.should_stop and self.state != AgentState.PAUSED:
                    if mining_task in done:
                        self.mc.postToChat("MinerBot: Mining finished here. Requirements not met. Execute fulfill again.") 
                        self.mining_position = None
                        self.ready_to_mine = False 
                        self.current_position.clear()
                
                for task in pending:
                    task.cancel()

            except asyncio.CancelledError:
                self.mc.postToChat("MinerBot: Mining task cancelled")
                self.is_mining = False
                raise
            except Exception as e:
                self.workspace.log_event(
                    "MINING_ERROR",
                    self.__class__.__name__,
                    {
                        "error": str(e),
                    }
                )
                self.set_state(AgentState.ERROR, reason=f"Mining error: {str(e)}")
                if self.mining_strategy:
                    self.mining_strategy.release_all_locks()
                self.is_mining = False
                self.mining_position = None
                self.ready_to_mine = False 
                self.current_position.clear()
    
    def handle_command(self, command):
        payload = command.get("payload", {})
        action = payload.get("action")
        parameters = payload.get("parameters", {})

        if super().handle_command(command):
            if action == "resume":
                if self.current_bom and not self.requirements_fulfilled():
                    self.ready_to_mine = True
                    self.mc.postToChat("MinerBot: Resuming mining execution...")
                return True
            return True
    
        if action == "set":
            self.args.update(parameters)
            if "strategy" in parameters:
                strategy = parameters["strategy"]
                if strategy in ["vertical", "grid", "vein"]:
                    self.mining_strategy_name = strategy
                    self.mining_strategy = None

                    if self.is_mining:
                        self.mining_event.set()
                        self.mc.postToChat(f"Interrupting current mining to switch to: {strategy}")
                    else:
                        self.mc.postToChat(f"Mining strategy set to: {strategy}")
                else:
                    self.mc.postToChat(f"Invalid strategy: {strategy}. Use vertical, grid, or vein.")
            return True
        elif action == "fulfill":
            self.ready_to_mine = True
            self.mc.postToChat("MinerBot: Starting mining execution...")
            return True
        elif action == "test":
            fake_message = {
                "type": "materials.requirements.v1",
                "source": "User",
                "payload": {
                    "requirements": parameters
                }
            }
            self.handle_material_requirements(fake_message)
            return True
            
        return False
    
    def handle_material_requirements(self, message):
        payload = message.get("payload", {})
        requirements = payload.get("requirements", {})
        self.material_requirements = requirements
        self.current_bom = message
        self.mining_position = None
        
        # Auto provide materials that do not need mining
        for material, qty in requirements.items():
            if material in AUTO_PROVIDED_MATERIALS:
                self.inventory[material] = qty
        
        self.workspace.log_event(
            "BOM_RECEIVED",
            self.__class__.__name__,
            {
                "source": message.get("source"),
                "requirements": self.material_requirements,
            }
        )
        
        minable_reqs = self.get_minable_requirements()
        if minable_reqs:
            self.mc.postToChat(f"MinerBot: Received requirements for {len(minable_reqs)} minable materials")
        
    def get_minable_requirements(self) -> dict:
        remaining = {m: max(0, q - self.inventory.get(m, 0)) for m, q in self.material_requirements.items() if m not in AUTO_PROVIDED_MATERIALS}
        ore_reqs = reduce(self.merge_ores, map(lambda kv: self.to_ore_req(*kv), remaining.items()), {})
        return {m: q for m, q in ore_reqs.items() if m in MINABLE_MATERIALS and q > 0}

    def to_ore_req(self, material, quantity):
        if material in PROCESSABLE_MATERIALS:
            return (PROCESSABLE_MATERIALS[material]["raw"], quantity * PROCESSABLE_MATERIALS[material]["amount"])
        return (material, quantity)
    
    def merge_ores(self, acc, kv):
        return {**acc, kv[0]: acc.get(kv[0], 0) + kv[1]}

    def convert_ores_to_blocks(self):
        for block_name, info in PROCESSABLE_MATERIALS.items():
            if block_name not in self.material_requirements:
                continue
            needed = self.material_requirements[block_name]
            ore_name, ore_per_block = info["raw"], info["amount"]
            available_ore = self.inventory.get(ore_name, 0)
            can_make = available_ore // ore_per_block
            to_convert = min(can_make, needed - self.inventory.get(block_name, 0))
            if to_convert > 0:
                self.inventory[ore_name] -= to_convert * ore_per_block
                self.inventory[block_name] = self.inventory.get(block_name, 0) + to_convert

    def validate_inventory(self) -> bool:
        for material, needed in self.material_requirements.items():
            if material in MINABLE_MATERIALS and self.inventory.get(material, 0) < needed:
                return False
        return True

    def requirements_fulfilled(self) -> bool:
        minable_reqs = self.get_minable_requirements()
        if not minable_reqs:
            return True
        
        for material, needed in minable_reqs.items():
            if needed > 0:
                return False
        return True

    def send_inventory_update(self, complete: bool = False):
        message = self.generate_message()
        message["payload"]["complete"] = complete
        message["payload"]["strategy"] = self.mining_strategy.get_strategy_name() if self.mining_strategy else None
        self.workspace.post_message(message)

    def get_block_names(self):
        return {b.id: name for name, b in block.__dict__.items() if hasattr(b, "id")}
     
    def generate_message(self):
        progress_payload = []

        for name, qty in self.material_requirements.items():
            collected = self.inventory.get(name, 0)
            progress_payload.append({
                "material": name,
                "required": qty,
                "collected": collected,
                "percentage": min((collected / qty) * 100, 100)
            })
        
        all_collected = all(self.inventory.get(mat, 0) >= qty for mat, qty in self.material_requirements.items())
        status = "COMPLETED" if all_collected else "IN_PROGRESS"

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"

        message = {
            "type": "inventory.v1",
            "source": "MinerBot",
            "target": "BuilderBot",
            "timestamp": timestamp,
            "payload": {
                "materials": progress_payload
            },
            "status": status,
            "context": {
                "task_id": str(id(self.pda_task)) if self.pda_task else None,
                "state": self.state.value
            }
        }
        return message
    
    def set_state(self, new_state: AgentState, reason: str = None):
        old_state = self.state
        super().set_state(new_state, reason)
        
        if new_state in [AgentState.STOPPED, AgentState.ERROR]:
            if self.mining_strategy:
                self.mining_strategy.release_all_locks()
            
            notification = {
                "type": "state_change.v1",
                "source": self.__class__.__name__,
                "target": "BuilderBot",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
                "payload": {
                    "previous_state": old_state.value,
                    "new_state": new_state.value,
                    "reason": reason
                }
            }
            self.workspace.post_message(notification)