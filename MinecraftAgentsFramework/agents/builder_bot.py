from base_agent import BaseAgent, AgentState
from utils import create_message
from functools import reduce
import mcpi.block as block
from nbt import nbt
import datetime
import asyncio
import os

class BuilderBot(BaseAgent):
    # Block mapping from Minecraft IDs to Mcpi block types
    BLOCK_MAP = {
        0: "AIR", 1: "STONE", 2: "GRASS",
        3: "DIRT", 4: "COBBLESTONE", 5: "WOOD_PLANKS",
        6: "SAPLING", 7: "BEDROCK", 8: "WATER",
        9: "WATER_STATIONARY", 10: "LAVA", 11: "LAVA_STATIONARY",
        12: "SAND", 13: "GRAVEL", 14: "GOLD_ORE",
        15: "IRON_ORE", 16: "COAL_ORE", 17: "WOOD",
        18: "LEAVES", 20: "GLASS", 21: "LAPIS_LAZULI_ORE",
        22: "LAPIS_LAZULI_BLOCK", 24: "SANDSTONE", 26: "BED",
        30: "COBWEB", 31: "GRASS_TALL", 35: "WOOL",
        37: "FLOWER_YELLOW", 38: "FLOWER_CYAN", 39: "MUSHROOM_BROWN",
        40: "MUSHROOM_RED", 41: "GOLD_BLOCK", 42: "IRON_BLOCK",
        43: "STONE_SLAB_DOUBLE", 44: "STONE_SLAB", 45: "BRICK_BLOCK",
        46: "TNT", 47: "BOOKSHELF", 48: "MOSS_STONE",
        49: "OBSIDIAN", 50: "TORCH", 51: "FIRE",
        53: "STAIRS_WOOD", 54: "CHEST", 56: "DIAMOND_ORE",
        57: "DIAMOND_BLOCK", 58: "CRAFTING_TABLE", 60: "FARMLAND",
        61: "FURNACE_INACTIVE", 62: "FURNACE_ACTIVE", 64: "DOOR_WOOD",
        65: "LADDER", 67: "STAIRS_COBBLESTONE", 71: "DOOR_IRON",
        73: "REDSTONE_ORE", 78: "SNOW", 79: "ICE",
        80: "SNOW_BLOCK", 81: "CACTUS", 82: "CLAY",
        83: "SUGAR_CANE", 85: "FENCE", 89: "GLOWSTONE_BLOCK",
        95: "BEDROCK_INVISIBLE", 98: "STONE_BRICK", 102: "GLASS_PANE",
        103: "MELON", 107: "FENCE_GATE", 246: "GLOWING_OBSIDIAN",
        247: "NETHER_REACTOR_CORE"
    }

    # Materials provided automatically which cannot be mined
    AUTO_PROVIDED = set({
        "GRASS", "DIRT", "GRAVEL", "SAND", "WOOD_PLANKS", "WOOD", "SANDSTONE", "WOOL",
        "LEAVES", "GLASS", "BRICK_BLOCK", "BOOKSHELF", "MOSS_STONE", "TORCH",
        "STAIRS_WOOD", "CHEST", "DOOR_WOOD", "LADDER", "STAIRS_COBBLESTONE",
        "FENCE", "GLOWSTONE_BLOCK", "STONE_BRICK", "GLASS_PANE", "FENCE_GATE"
    })

    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.mc = mc
        self.workspace = workspace
        self.current_plan = None
        self.structured_blocks = {}
        self.bom = {}                       # Bill of Materials
        self.inventory = {}                 # Materials received from Miner bot
        self.build_position = None          # Build start coordinates
        self.checkpoint = {"layer": 0, "block_idx": 0}
        self.is_building = False
        self.build_ready = False
        self.terrain_data = None
        self.requirements_published = False

    async def perceive(self, **kwargs):
        """Process messages from other agents"""
        for msg in self.get_messages():
            msg_type = msg.get("type", "")
            if msg_type == "map.v1":
                self.terrain_data = msg.get("payload")
                self.mc.postToChat("Builder agent has received terrain data from exploration")
            elif msg_type == "inventory.v1":
                for item in msg.get("payload", {}).get("materials", []):
                    self.inventory[item["material"]] = item["collected"]
                is_complete = msg.get("payload", {}).get("complete", False)
                if is_complete:
                    self.mc.postToChat(f"Builder agent has received inventory update of {len(msg.get('payload', {}).get('materials', []))} materials")
                    if self._materials_ready():
                        self.mc.postToChat("Builder agent has received all necessary materials")
                        self.requirements_published = False

    async def decide(self, **kwargs):
        """Decide next agent state based on conditions"""
        if not self.current_plan:
            return
        if not self._materials_ready() and self.state != AgentState.WAITING:
            self.set_state(AgentState.WAITING, "Waiting materials for building")
        elif self.build_ready and not self.is_building and self.state != AgentState.RUNNING:
            self.set_state(AgentState.RUNNING, "Ready to build the structure")

    async def act(self, **kwargs):
        """Check if agent can start building"""
        if not self.build_ready or self.is_building or not self._materials_ready():
            await asyncio.sleep(0.5)
            return
        
        await self._execute_build_process()
    
    @staticmethod
    def _discover_plans():
        """Find schematic plans in schematics directory"""
        schematics_dir = os.path.join(os.path.dirname(__file__), "..", "schematics")
        # Remove file extension (6 chars)
        return [f[:-6] for f in os.listdir(schematics_dir) if f.endswith(".schem")] if os.path.exists(schematics_dir) else []
    
    def _load_schematic(self, template: str) -> dict:
        """Load schematic file and parse NBT (Named Binary Tag) data"""
        path = os.path.join(os.path.dirname(__file__), "..", "schematics", f"{template}.schem")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Schematic template not found: {template}")

        nbt_to_dict = lambda tag: (
            {k: nbt_to_dict(v) for k, v in tag.items()} if isinstance(tag, nbt.TAG_Compound) else
            [nbt_to_dict(i) for i in tag] if isinstance(tag, nbt.TAG_List) else
            list(tag.value) if isinstance(tag, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)) else
            tag.value
        )
        return nbt_to_dict(nbt.NBTFile(path, 'rb'))

    def _structure_blocks(self, schem: dict) -> dict:
        """Transform schematic parsed data to layered block structure"""
        w, h, l = schem['Width'], schem['Height'], schem['Length']
        blocks = schem.get('Blocks', [])
        block_data = schem.get('Data', [])
        
        def block_at(x, y, z):
            idx = (y * l + z) * w + x
            if idx >= len(blocks):
                return None
            block_id = blocks[idx]
            if block_id < 0:
                block_id = block_id + 256
            mc_blk = self.BLOCK_MAP.get(block_id, "STONE")
            mc_data = block_data[idx] if idx < len(block_data) else 0
            return None if mc_blk == "AIR" else {"x": x, "z": z, "block": mc_blk, "data": mc_data}

        layers = {y: list(filter(None, [block_at(x, y, z) for z in range(l) for x in range(w)])) for y in range(h)}
        # Return only layers with blocks
        return {y: blks for y, blks in layers.items() if blks}

    def _compute_bom(self) -> dict:
        """Compute Bill of Materials aggregating block counts"""
        all_blocks = [b for layer in self.structured_blocks.values() for b in layer]
        return reduce(lambda acc, b: {**acc, b["block"]: acc.get(b["block"], 0) + 1}, all_blocks, {})

    def _pending_materials(self) -> dict:
        """Filter Bill of Materials to find missing materials"""
        return {material: amount - self.inventory.get(material, 0) for material, amount in self.bom.items()
                if material not in self.AUTO_PROVIDED and amount > self.inventory.get(material, 0)}

    def _materials_ready(self) -> bool:
        return not self._pending_materials()

    def _find_build_position(self) -> tuple:
        """Find the smallest flat region that fits the structure dimensions"""
        if not self.terrain_data or not self.structured_blocks:
            return None
        
        regions = self.terrain_data.get("regions", [])
        if not regions:
            return None
        
        # Calculate structure dimensions from schematic
        all_blocks = [b for layer in self.structured_blocks.values() for b in layer]
        struct_width = max(b["x"] for b in all_blocks) + 1 if all_blocks else 0
        struct_depth = max(b["z"] for b in all_blocks) + 1 if all_blocks else 0
        
        # Filter regions that can fit the structure
        fitting_regions = list(filter(
            lambda r: r.get("width", 0) >= struct_width and r.get("depth", 0) >= struct_depth,
            regions
        ))
        
        if not fitting_regions:
            return None
        
        # Find smallest fitting region by area
        best_region = min(fitting_regions, key=lambda r: r.get("width", 0) * r.get("depth", 0))
        
        # Get the first block position for build origin
        blocks = best_region.get("blocks", [])
        if not blocks:
            return None
        
        origin = min(blocks, key=lambda b: (b["x"], b["z"]))
        return (origin["x"], best_region["y"], origin["z"])
    
    def _save_checkpoint(self):
        self.workspace.log_event("CHECKPOINT", self.__class__.__name__, {
            "plan": self.current_plan, **self.checkpoint, "inventory": self.inventory
        })
    
    def _publish_requirements(self):
        """Publish materials requirements to Miner bot"""
        pending = self._pending_materials()
        if not pending:
            return
        if self.requirements_published:
            self.mc.postToChat("Builder agent is still waiting for materials from mining")
            return
        
        # Calculate target build position for Miner coordination
        reference_position = self._find_build_position()
        
        self.requirements_published = True
        context = {
            "task_id": str(id(self.pda_task)) if self.pda_task else None,
            "state": self.state.value
        }
        
        payload = {"requirements": pending}
        if reference_position:
            payload["reference_position"] = reference_position

        message = create_message(
            "materials.requirements.v1", 
            self.__class__.__name__, 
            "MinerBot", 
            payload,
            status="PENDING",
            context=context
        )
        self.workspace.post_message(message)
        self.mc.postToChat(f"Builder agent has sent Bill Of Materials for mining ({len(pending)} block types)")

    def _publish_progress(self, status: str):
        """Publish build progress to Miner Bot"""
        total = sum(len(l) for l in self.structured_blocks.values())
        placed = sum(len(self.structured_blocks.get(y, [])) for y in sorted(self.structured_blocks)[:self.checkpoint["layer"]]) + self.checkpoint["block_idx"]
        
        context = {
            "task_id": str(id(self.pda_task)) if self.pda_task else None,
            "state": self.state.value
        }
        message = create_message(
            "build.v1",
            self.__class__.__name__,
            "MinerBot",
            {
                "plan": self.current_plan,
                "progress": {"placed": placed, "total": total}
            },
            status=status,
            context=context
        )
        self.workspace.post_message(message)

    async def _execute_build_process(self):
        """Place blocks layer by layer with checkpoints"""
        start = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        self.workspace.log_event("BUILD_STARTED", self.__class__.__name__, {"timestamp": start})
        
        try:
            self.is_building = True
            self._publish_progress("IN_PROGRESS")
            sorted_y = sorted(self.structured_blocks.keys())
            bx, by, bz = self.build_position

            for layer_id, y_coord in enumerate(sorted_y[self.checkpoint["layer"]:], self.checkpoint["layer"]):
                block_start_index = self.checkpoint["block_idx"] if layer_id == self.checkpoint["layer"] else 0
                for block_idx, blk in enumerate(self.structured_blocks[y_coord][block_start_index:], block_start_index):
                    # Save build progress if agent is paused or stopped
                    if self.state == AgentState.PAUSED or self.should_stop:
                        self.checkpoint = {"layer": layer_id, "block_idx": block_idx}
                        self._save_checkpoint()
                        self.is_building = False
                        end = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
                        self.workspace.log_event("BUILD_COMPLETED", self.__class__.__name__, {"timestamp": end})
                        return

                    # Place blocks one by one
                    b = getattr(block, blk["block"], block.STONE)
                    self.mc.setBlock(bx + blk["x"], by + y_coord, bz + blk["z"], b.id, blk["data"])
                    await asyncio.sleep(0.02)

                self.checkpoint = {"layer": layer_id + 1, "block_idx": 0}
                self._save_checkpoint()
            
            self._publish_progress("COMPLETED")
            self.mc.postToChat("Builder agent has finished building")
            self._save_checkpoint()
            end = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            self.workspace.log_event("BUILD_COMPLETED", self.__class__.__name__, {"timestamp": end})
            self.build_ready = False
            self.terrain_data = None
            self.inventory.clear()
            self.build_position = None
            self.checkpoint = {"layer": 0, "block_idx": 0}

        except Exception as e:
            self.workspace.log_event("BUILD_ERROR", self.__class__.__name__, {"error": str(e)})
            self.set_state(AgentState.ERROR, str(e))
        finally:
            self.is_building = False
    
    def handle_command(self, command):
        payload = command.get("payload", {})
        action, params = payload.get("action"), payload.get("parameters", {})

        if super().handle_command(command):
            if action == "resume" and self.current_plan:
                self.mc.postToChat("Builder agent has resumed building from checkpoint")
            return True

        actions = {"plan": self._plan, "bom": self._bom, "build": self._build}
        if action in actions:
            actions[action](params)
            return True
        return False

    def _plan(self, params):
        """Process plan commands: list and set"""
        if "list" in params or not params:
            plans = self._discover_plans()
            for p in (["Available Plans:"] + plans if plans else ["Available Plans: None"]): self.mc.postToChat(p)
            return

        template = params.get("set")
        if template:
            try:
                self.structured_blocks = self._structure_blocks(self._load_schematic(template))
                self.bom = self._compute_bom()
                self.current_plan = template
                self.checkpoint = {"layer": 0, "block_idx": 0}
                self.build_position = None
                self.build_ready = False
                self.requirements_published = False
                self.inventory.clear()
                self.args.update({"plan": template})
                total = sum(len(l) for l in self.structured_blocks.values())
                self.mc.postToChat(f"Template '{template}' has been loaded with {total} blocks")
                self._publish_requirements()
            except FileNotFoundError:
                self.mc.postToChat(f"Template '{template}' not found.")

    def _bom(self, _):
        """Display Bill of Materials"""
        if not self.bom:
            self.mc.postToChat("Builder agent has no plan set. Set a plan to view the Bill of Materials.")
            return
        self.mc.postToChat("=== Bill of Materials ===")
        # Sorted by quantity descending
        for m, q in sorted(self.bom.items(), key=lambda x: -x[1]):
            s = "✓" if m in self.AUTO_PROVIDED or self.inventory.get(m, 0) >= q else f"{self.inventory.get(m, 0)}/{q}"
            self.mc.postToChat(f"  {m}: {q} [{s}]")

    def _build(self, _):
        """Start building the structure"""
        if not self.current_plan:
            self.mc.postToChat("Builder agent has no plan set. Please set a plan first.")
            return
        if not self._materials_ready():
            self.mc.postToChat(f"Builder agent is waiting for {len(self._pending_materials())} materials")
            return
        if not self.terrain_data:
            self.mc.postToChat("Builder agent is waiting for terrain data from exploration")
            return
        
        # Find best fitting position from terrain data
        self.build_position = self._find_build_position()
        if not self.build_position:
            self.mc.postToChat("Builder agent has not found any suitable flat surface in the explored area")
            return
        
        self.build_ready = True
        self.mc.postToChat(f"Builder agent has started building the structure at {self.build_position}")

    def help(self):
        for line in [
            f"Agent {self.__class__.__name__} help commands:",
            "  ./builder plan list                  - List schematics",
            "  ./builder plan set <template>        - Load template",
            "  ./builder bom                        - Show materials",
            "  ./builder build                      - Build structure",
            "  ./builder pause                      - Pause building",
            "  ./builder resume                     - Resume building",
            "  ./builder stop                       - Stop agent",
            "  ./builder status                     - Show status",
        ]:
            self.mc.postToChat(line)