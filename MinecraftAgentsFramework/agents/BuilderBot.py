from BaseAgent import BaseAgent, AgentState
from functools import reduce
import mcpi.block as block
from nbt import nbt
import datetime
import asyncio
import os

class BuilderBot(BaseAgent):
    # Block mapping from Minecraft IDs to Mcpi block types
    BLOCK_MAP = {
        "minecraft:air": ("AIR", 0), "minecraft:stone": ("STONE", 0),
        "minecraft:grass_block": ("GRASS", 0), "minecraft:dirt": ("DIRT", 0),
        "minecraft:cobblestone": ("COBBLESTONE", 0), "minecraft:oak_planks": ("WOOD_PLANKS", 0),
        "minecraft:spruce_planks": ("WOOD_PLANKS", 1), "minecraft:birch_planks": ("WOOD_PLANKS", 2),
        "minecraft:jungle_planks": ("WOOD_PLANKS", 3), "minecraft:oak_log": ("WOOD", 0),
        "minecraft:spruce_log": ("WOOD", 1), "minecraft:birch_log": ("WOOD", 2),
        "minecraft:jungle_log": ("WOOD", 3), "minecraft:oak_leaves": ("LEAVES", 1),
        "minecraft:spruce_leaves": ("LEAVES", 2), "minecraft:birch_leaves": ("LEAVES", 3),
        "minecraft:glass": ("GLASS", 0), "minecraft:sandstone": ("SANDSTONE", 0),
        "minecraft:white_wool": ("WOOL", 0), "minecraft:orange_wool": ("WOOL", 1),
        "minecraft:yellow_wool": ("WOOL", 4), "minecraft:gold_block": ("GOLD_BLOCK", 0),
        "minecraft:iron_block": ("IRON_BLOCK", 0), "minecraft:brick_block": ("BRICK_BLOCK", 0),
        "minecraft:bookshelf": ("BOOKSHELF", 0), "minecraft:mossy_cobblestone": ("MOSS_STONE", 0),
        "minecraft:obsidian": ("OBSIDIAN", 0), "minecraft:torch": ("TORCH", 0),
        "minecraft:oak_stairs": ("STAIRS_WOOD", 0), "minecraft:chest": ("CHEST", 0),
        "minecraft:diamond_ore": ("DIAMOND_ORE", 0), "minecraft:diamond_block": ("DIAMOND_BLOCK", 0),
        "minecraft:crafting_table": ("CRAFTING_TABLE", 0), "minecraft:furnace": ("FURNACE_INACTIVE", 0),
        "minecraft:oak_door": ("DOOR_WOOD", 0), "minecraft:ladder": ("LADDER", 0),
        "minecraft:cobblestone_stairs": ("STAIRS_COBBLESTONE", 0), "minecraft:iron_door": ("DOOR_IRON", 0),
        "minecraft:oak_fence": ("FENCE", 0), "minecraft:glowstone": ("GLOWSTONE_BLOCK", 0),
        "minecraft:stone_bricks": ("STONE_BRICK", 0), "minecraft:glass_pane": ("GLASS_PANE", 0),
        "minecraft:oak_fence_gate": ("FENCE_GATE", 0), "minecraft:sand": ("SAND", 0),
        "minecraft:gravel": ("GRAVEL", 0), "minecraft:gold_ore": ("GOLD_ORE", 0),
        "minecraft:iron_ore": ("IRON_ORE", 0), "minecraft:coal_ore": ("COAL_ORE", 0),
        "minecraft:redstone_ore": ("REDSTONE_ORE", 0), "minecraft:lapis_ore": ("LAPIS_LAZULI_ORE", 0),
        "minecraft:lapis_block": ("LAPIS_LAZULI_BLOCK", 0), "minecraft:tnt": ("TNT", 0),
        "minecraft:snow": ("SNOW", 0), "minecraft:ice": ("ICE", 0), "minecraft:cactus": ("CACTUS", 0),
        "minecraft:clay": ("CLAY", 0), "minecraft:melon": ("MELON", 0), "minecraft:bedrock": ("BEDROCK", 0),
        "minecraft:water": ("WATER", 0), "minecraft:lava": ("LAVA", 0),
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
                if self._materials_ready() and self.build_ready:
                    self.mc.postToChat("Builder agent has received all necessary materials")

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
        palette = {v: k for k, v in schem['Palette'].items()}
        data = schem['BlockData']

        def block_at(x, y, z):
            idx = (y * l + z) * w + x
            if idx >= len(data):
                return None
            name = palette.get(data[idx], "minecraft:air").split('[')[0]
            mc_blk, mc_data = self.BLOCK_MAP.get(name, ("STONE", 0))
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
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        self.workspace.post_message({
            "type": "materials.requirements.v1",
            "source": self.__class__.__name__,
            "target": "MinerBot",
            "timestamp": timestamp,
            "payload": {
                "requirements": pending
            },
            "status": "PENDING",
            "context": {
                "task_id": str(id(self.pda_task)) if self.pda_task else None,
                "state": self.state.value
            }
        })
        self.mc.postToChat(f"Builder agent has sent Bill Of Materials for mining ({len(pending)} block types)")

    def _publish_progress(self, status: str):
        """Publish build progress to Miner Bot"""
        total = sum(len(l) for l in self.structured_blocks.values())
        placed = sum(len(self.structured_blocks.get(y, [])) for y in sorted(self.structured_blocks)[:self.checkpoint["layer"]]) + self.checkpoint["block_idx"]
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        self.workspace.post_message({
            "type": "build.v1",
            "source": self.__class__.__name__,
            "target": "MinerBot",
            "timestamp": timestamp,
            "payload": {
                "plan": self.current_plan,
                "progress": {"placed": placed, "total": total}
            },
            "status": status,
            "context": {
                "task_id": str(id(self.pda_task)) if self.pda_task else None,
                "state": self.state.value
            }
        })

    async def _execute_build_process(self):
        """Place blocks layer by layer with checkpoints"""
        start = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        self.workspace.log_event("BUILD_STARTED", self.__class__.__name__, {"timestamp": start})
        
        try:
            if not self.build_position:
                pos = self.mc.player.getTilePos()   # Use current player position
                self.build_position = (pos.x, pos.y, pos.z)
                self.mc.postToChat(f"Builder agent starting building at {self.build_position}")

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
                    await asyncio.sleep(0.1)

                self.checkpoint = {"layer": layer_id + 1, "block_idx": 0}
                self._save_checkpoint()
            
            self._publish_progress("COMPLETED")
            self.mc.postToChat("Builder agent has finished building")
            self._save_checkpoint()
            end = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            self.workspace.log_event("BUILD_COMPLETED", self.__class__.__name__, {"timestamp": end})

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
                self.mc.postToChat("Builder bot has resumed building from checkpoint")
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
                total = sum(len(l) for l in self.structured_blocks.values())
                self.mc.postToChat(f"Template '{template}' has been loaded with {total} blocks")
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
            self._publish_requirements()
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