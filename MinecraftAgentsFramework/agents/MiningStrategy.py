from abc import ABC, abstractmethod
from BaseAgent import AgentState
import datetime
import asyncio
import mcpi.block as block
from collections import deque

class MiningStrategy(ABC):
    def __init__(self, mc, agent_id, workspace, agent=None):
        self.mc = mc
        self.agent_id = agent_id
        self.agent = agent
        self.workspace = workspace
        self.collected_materials = {}
        self.locked_regions = set()
        self.block_names = self.get_block_names()
    
    @abstractmethod
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        pass
    
    def should_stop_mining(self) -> bool:
        if not self.agent:
            return False
        return self.agent.should_stop or self.agent.state == AgentState.STOPPED
    
    def lock_region(self, x: int, z: int) -> bool:
        sector = (x, z)
        if sector in self.locked_regions:
            return False
        self.locked_regions.add(sector)
        self.workspace.log_event(
            "REGION_LOCKED",
            self.agent_id,
            {
                "sector": sector,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            }
        )
        return True
    
    def release_all_locks(self):
        if self.locked_regions:
            self.workspace.log_event(
                "REGIONS_RELEASED",
                self.agent_id,
                {
                    "sectors": list(self.locked_regions),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
                }
            )
            self.locked_regions.clear()
    
    def update_collected_materials(self, material: str, quantity: int):
        if material not in self.collected_materials:
            self.collected_materials[material] = 0
        self.collected_materials[material] += quantity
    
    def requirements_met(self, requirements: dict) -> bool:
        for material, needed in requirements.items():
            if self.collected_materials.get(material, 0) < needed:
                return False
        return True
    
    def get_material_name(self, block_id: int) -> str:
        return self.block_names.get(block_id, f"UNKNOWN_{block_id}")
    
    def get_block_names(self):
        return {b.id: name for name, b in block.__dict__.items() if hasattr(b, "id")}


class VerticalSearchStrategy(MiningStrategy):
    def __init__(self, mc, agent_id, workspace, agent=None):
        super().__init__(mc, agent_id, workspace, agent=agent)
        self.bedrock_level = 5 
    
    def get_strategy_name(self) -> str:
        return "VerticalSearch"
    
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        self.collected_materials.clear()
        x, target_y, z = start_position
        current_y = self.mc.getHeight(x, z)
        last_y = current_position.get("y", 0)
        
        if target_y is None or target_y < 0:
            target_y = self.bedrock_level
        else:
            target_y = max(target_y, self.bedrock_level)
        
        is_resuming = (last_y != 0)
        if is_resuming:
            resume_y = last_y
            resume_y = max(target_y, min(resume_y, current_y))
            self.mc.postToChat(f"VerticalSearch: Resuming mining at ({x}, {resume_y}, {z})")
            self.workspace.log_event(
                "MINING_RESUMED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "resume_position": (x, resume_y, z),
                    "target_y": target_y,
                    "requirements": requirements
                }
            )
        else: 
            resume_y = current_y
            self.mc.postToChat(f"VerticalSearch: Mining from {current_y} down to {target_y} at ({x}, {z})")
            self.workspace.log_event(
                "MINING_STARTED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "start_position": (x, current_y, z),
                    "target_y": target_y,
                    "requirements": requirements
                }
            )
        

        if not self.lock_region(x, z):
            self.workspace.log_event(
                "REGION_LOCK_FAILED",
                self.agent_id,
                {"position": start_position, "strategy": self.get_strategy_name()}
            )
            return self.collected_materials
        
        try:
            blocks_checked = await self.mine_column(x, resume_y, z, target_y, requirements, current_position)
            
            self.mc.postToChat(f"VerticalSearch: Completed column at ({x}, {z})")

            self.workspace.log_event(
                "MINING_COMPLETED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "collected": self.collected_materials,
                    "blocks_checked": blocks_checked,
                    "requirements_met": self.requirements_met(requirements)
                }
            )
        
        finally:
            self.release_all_locks()
        
        return self.collected_materials
    
    async def mine_column(self, x: int, start_y: int, z: int, target_y: int, requirements: dict, current_position: dict):
        blocks_checked = 0
        for y in range(start_y, target_y - 1, -1):
            await asyncio.sleep(0)
            if self.should_stop_mining():
                self.workspace.log_event("MINING_INTERRUPTED", self.agent_id, {"position": (x, y, z), "reason": "Agent stopped"})
                break

            current_position['x'] = 0
            current_position['y'] = y
            current_position['z'] = 0
            block_type = self.mc.getBlock(x, y, z)
            blocks_checked += 1
            
            if block_type == 0:
                continue
            
            material_name = self.get_material_name(block_type)
            
            self.mc.setBlock(x, y, z, 0)
            
            if material_name in requirements:
                self.mc.postToChat(f"VerticalSearch: Found {material_name} at ({x}, {y}, {z})")
                self.update_collected_materials(material_name, 1)
                self.workspace.log_event(
                    "BLOCK_MINED",
                    self.agent_id,
                    {
                        "position": (x, y, z),
                        "material": material_name,
                        "strategy": self.get_strategy_name()
                    }
                )
            if self.requirements_met(requirements):
                break
        return blocks_checked


class GridSearchStrategy(MiningStrategy):
    def __init__(self, mc, agent_id, workspace, agent=None):
        super().__init__(mc, agent_id, workspace, agent=agent)
        self.bedrock_level = 5
    
    def get_strategy_name(self) -> str:
        return "GridSearch"
    
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        self.collected_materials.clear()
        x, target_y, z = start_position
        range_x = coords.get("x", 0)
        range_z = coords.get("z", 0)

        last_x = current_position.get("x", 0)
        last_y = current_position.get("y", 0)
        last_z = current_position.get("z", 0)
        
        current_y = self.mc.getHeight(x, z)
        
        if target_y is None or target_y < 0:
            target_y = self.bedrock_level
        else:
            target_y = max(target_y, self.bedrock_level)
        
        start_x = int(x - range_x)
        end_x = int(x + range_x)
        start_z = int(z - range_z)
        end_z = int(z + range_z)

        is_resuming = (last_x != 0 or last_y != 0 or last_z != 0)

        if is_resuming:
            resume_x = start_x + last_x
            resume_z = start_z + last_z
            resume_y = last_y

            resume_x = max(start_x, min(resume_x, end_x))
            resume_z = max(start_z, min(resume_z, end_z))
            resume_y = max(target_y, min(resume_y, current_y))
        
            self.mc.postToChat(f"GridSearch: Resuming mining at ({resume_x}, {resume_y}, {resume_z})")
            
            self.workspace.log_event(
                "MINING_RESUMED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "resume_position": (resume_x, resume_y, resume_z),
                    "bounds": {
                        "x": (start_x, end_x),
                        "y": (target_y, current_y),
                        "z": (start_z, end_z)
                    },
                    "requirements": requirements
                }
            )
        else: 
            resume_x = start_x
            resume_z = start_z
            resume_y = current_y

            self.mc.postToChat(f"GridSearch: Mining area {range_x}x{range_z} from {current_y} down to {target_y}")
            self.workspace.log_event(
                "MINING_STARTED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "bounds": {
                        "x": (start_x, end_x),
                        "y": (target_y, current_y),
                        "z": (start_z, end_z)
                    },
                    "requirements": requirements
                }
            )
        
        if not self.lock_region(x, z):
            self.workspace.log_event(
                "REGION_LOCK_FAILED",
                self.agent_id,
                {"position": start_position, "strategy": self.get_strategy_name()}
            )
            return self.collected_materials
        
        try:
            blocks_checked = 0
            started_mining = False
            for x in range(start_x, end_x + 1):
                for z in range(start_z, end_z + 1):
                    if self.requirements_met(requirements):
                        break

                    if is_resuming and not started_mining:
                        if x < resume_x or (x == resume_x and z < resume_z):
                            continue
                        if x == resume_x and z == resume_z:
                            start_y_column = resume_y
                            started_mining = True
                        else:
                            start_y_column = current_y
                            started_mining = True
                    else:
                        start_y_column = current_y

                    for y in range(start_y_column, target_y - 1, -1):
                        await asyncio.sleep(0)
                        if self.should_stop_mining():
                            self.workspace.log_event("MINING_INTERRUPTED", self.agent_id, {"position": (x, y, z), "reason": "Agent stopped"})
                            break

                        current_position['x'] = x - start_x
                        current_position['y'] = y
                        current_position['z'] = z - start_z

                        block_type = self.mc.getBlock(x, y, z)
                        blocks_checked += 1
                        
                        if block_type == 0:
                            continue
                        
                        material_name = self.get_material_name(block_type)
                        
                        self.mc.setBlock(x, y, z, 0)
                        
                        if material_name in requirements:
                            self.mc.postToChat(f"GridSearch: Found {material_name} at ({x}, {y}, {z})")
                            self.update_collected_materials(material_name, 1)
                            self.workspace.log_event(
                                "BLOCK_MINED",
                                self.agent_id,
                                {
                                    "position": (x, y, z),
                                    "material": material_name,
                                    "strategy": self.get_strategy_name()
                                }
                            )
                    if self.should_stop_mining():
                        break
                if self.should_stop_mining():
                    break
            
            self.workspace.log_event(
                "MINING_COMPLETED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "blocks_checked": blocks_checked,
                    "collected": self.collected_materials
                }
            )
        
        finally:
            self.release_all_locks()
        return self.collected_materials
    
class VeinSearchStrategy(MiningStrategy):
    def __init__(self, mc, agent_id, workspace, agent=None):
        super().__init__(mc, agent_id, workspace, agent=agent)
        self.max_vein_size = 20
        self.visited = set()
        self.bedrock_level = 5
        self.vein_queue = []  # persistent queue for vein blocks
        self.veins_found = 0
    
    def get_strategy_name(self) -> str:
        return "VeinSearch"
    
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        self.collected_materials.clear()
        
        start_x, target_y, start_z = start_position
        current_y = self.mc.getHeight(start_x, start_z)
        
        last_x = current_position.get("x", 0)
        last_y = current_position.get("y", 0)
        last_z = current_position.get("z", 0)
        
        if target_y is None or target_y < 0:
            target_y = self.bedrock_level
        else:
            target_y = max(target_y, self.bedrock_level)
        
        is_resuming = (last_x != 0 or last_y != 0 or last_z != 0)
        
        if is_resuming:
            resume_x = start_x + last_x
            resume_y = last_y
            resume_z = start_z + last_z
            
            resume_y = max(target_y, min(resume_y, current_y))
            
            self.mc.postToChat(f"VeinSearch: Resuming mining at ({resume_x}, {resume_y}, {resume_z})")
            
            self.workspace.log_event(
                "MINING_RESUMED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "resume_position": (resume_x, resume_y, resume_z),
                    "target_y": target_y,
                    "requirements": requirements
                }
            )
        else:
            resume_x = start_x
            resume_y = current_y
            resume_z = start_z
            
            self.mc.postToChat(f"VeinSearch: Starting mining from ({start_x}, {current_y}, {start_z}) down to {target_y}")
            
            self.workspace.log_event(
                "MINING_STARTED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "start_position": (start_x, current_y, start_z),
                    "target_y": target_y,
                    "requirements": requirements
                }
            )

        if not self.lock_region(start_x, start_z):
            self.workspace.log_event(
                "REGION_LOCK_FAILED",
                self.agent_id,
                {"position": start_position, "strategy": self.get_strategy_name()}
            )
            return self.collected_materials
        
        try:
            self.visited.clear()
            blocks_checked = 0
            
            x, y, z = resume_x, resume_y, resume_z
            
            staircase_pattern = [
                (0, 0, 0), (1, 0, 0),
                (0, 1, 0), (1, 1, 0),
                (0, 2, 0), (1, 2, 0)
            ]
            
            # staircase mining pattern
            while y > target_y:
                if self.requirements_met(requirements):
                    break
                
                if self.should_stop_mining():
                    self.workspace.log_event(
                        "MINING_INTERRUPTED", 
                        self.agent_id, 
                        {"position": (x, y, z), "reason": "Agent stopped"}
                    )
                    break
                
                for dx, dy, dz in staircase_pattern:
                    if self.requirements_met(requirements) or self.should_stop_mining():
                        break
                    
                    block_x = x + dx
                    block_y = y + dy
                    block_z = z + dz
                    
                    current_position['x'] = block_x - start_x
                    current_position['y'] = block_y
                    current_position['z'] = block_z - start_z
                    
                    await self.process_block(block_x, block_y, block_z, requirements)
                    blocks_checked += 1
                    
                    if blocks_checked % 16 == 0:
                        await asyncio.sleep(0)
                        if self.should_stop_mining():
                            break
                
                if self.should_stop_mining():
                    break
                
                y -= 1
                z += 1

                current_position['x'] = x - start_x
                current_position['y'] = y
                current_position['z'] = z - start_z
                
                await asyncio.sleep(0.05)
            
            self.mc.postToChat(f"VeinSearch: Completed staircase mining. Veins found: {self.veins_found}")
            
            self.workspace.log_event(
                "MINING_COMPLETED",
                self.agent_id,
                {
                    "strategy": self.get_strategy_name(),
                    "veins_found": self.veins_found,
                    "blocks_checked": blocks_checked,
                    "collected": self.collected_materials,
                    "requirements_met": self.requirements_met(requirements)
                }
            )
        
        finally:
            self.release_all_locks()
        
        return self.collected_materials
    
    async def process_block(self, x: int, y: int, z: int, requirements: dict):
        if y < self.bedrock_level:
            return
        
        if self.requirements_met(requirements):
            return
        
        if self.vein_queue:
            await self.mine_vein_bfs(requirements)
            return
        
        block_type = self.mc.getBlock(x, y, z)
        
        if block_type == 0:
            return
        
        material_name = self.get_material_name(block_type)
        
        if material_name in requirements and (x, y, z) not in self.visited:
            self.veins_found += 1
            self.mc.postToChat(f"VeinSearch: Found vein #{self.veins_found} of {material_name} at ({x}, {y}, {z})")
            self.vein_queue.append((x, y, z, block_type, material_name))
            await self.mine_vein_bfs(requirements)
        else:
            self.mc.setBlock(x, y, z, 0)
    
    async def mine_vein_bfs(self, requirements: dict):
        if not isinstance(self.vein_queue, deque):
            self.vein_queue = deque(self.vein_queue)
        
        blocks_in_vein = 0
        
        while self.vein_queue and blocks_in_vein < self.max_vein_size:
            if self.requirements_met(requirements):
                break
            
            if self.should_stop_mining():
                self.mc.postToChat(f"VeinSearch: Pausing vein exploration. {len(self.vein_queue)} blocks in queue.")
                break
            
            curr_x, curr_y, curr_z, target_block_id, material = self.vein_queue.popleft()
            
            if (curr_x, curr_y, curr_z) in self.visited:
                continue
            
            if curr_y < self.bedrock_level:
                continue
                
            self.visited.add((curr_x, curr_y, curr_z))
            
            block_type = self.mc.getBlock(curr_x, curr_y, curr_z)
            if block_type == target_block_id:
                self.mc.setBlock(curr_x, curr_y, curr_z, 0)
                self.update_collected_materials(material, 1)
                blocks_in_vein += 1
                
                self.workspace.log_event(
                    "BLOCK_MINED",
                    self.agent_id,
                    {
                        "position": (curr_x, curr_y, curr_z),
                        "material": material,
                        "strategy": self.get_strategy_name(),
                        "vein_size": blocks_in_vein
                    }
                )
                
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        for dz in [-1, 0, 1]:
                            if dx == 0 and dy == 0 and dz == 0:
                                continue
                            adj_x = curr_x + dx
                            adj_y = curr_y + dy
                            adj_z = curr_z + dz
                            
                            if (adj_x, adj_y, adj_z) not in self.visited:
                                self.vein_queue.append((adj_x, adj_y, adj_z, target_block_id, material))
                
                if blocks_in_vein % 5 == 0:
                    await asyncio.sleep(0.02)
        
        if blocks_in_vein > 0 and not self.vein_queue:
            self.mc.postToChat(f"VeinSearch: Completed vein of {blocks_in_vein} {material} blocks")
        
        self.vein_queue = list(self.vein_queue)