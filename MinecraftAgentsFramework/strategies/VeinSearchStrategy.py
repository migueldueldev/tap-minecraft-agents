from .MiningStrategy import MiningStrategy
import asyncio
from collections import deque

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
        
        # Determine mining direction on X axis (default to 1: Positive X)
        dir_x = coords.get("direction_x", 1)
        
        try:
            self.visited.clear()
            blocks_checked = 0
            
            x, y, z = resume_x, resume_y, resume_z
            
            # Apply direction to the staircase pattern
            staircase_pattern = [
                (0, 0, 0), (1 * dir_x, 0, 0),
                (0, 1, 0), (1 * dir_x, 1, 0),
                (0, 2, 0), (1 * dir_x, 2, 0)
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
