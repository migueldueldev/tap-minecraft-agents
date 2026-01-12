from .mining_strategy import MiningStrategy
import asyncio

class GridSearchStrategy(MiningStrategy):
    def __init__(self, mc, agent_id, workspace, agent=None):
        super().__init__(mc, agent_id, workspace, agent=agent)
        self.bedrock_level = 5
    
    def get_strategy_name(self) -> str:
        return "GridSearch"
    
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        self.collected_materials.clear()
        
        center_x, target_y, center_z = start_position
        
        radius = coords.get("range", 32)
        range_x = radius
        range_z = radius

        last_x = current_position.get("x", 0)
        last_y = current_position.get("y", 0)
        last_z = current_position.get("z", 0)
        
        current_y = self.mc.getHeight(center_x, center_z)
        
        if target_y is None or target_y < 0:
            target_y = self.bedrock_level
        else:
            target_y = max(target_y, self.bedrock_level)
        
        start_x = int(center_x - range_x)
        end_x = int(center_x + range_x)
        start_z = int(center_z - range_z)
        end_z = int(center_z + range_z)

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

            self.mc.postToChat(f"GridSearch: Mining area {radius*2}x{radius*2} (Center: {center_x}, {center_z}) from {current_y} down to {target_y}")
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
                    "center": (center_x, center_z),
                    "range": radius,
                    "requirements": requirements
                }
            )
        
        if not self.lock_region(center_x, center_z): 
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
