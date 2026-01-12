from .mining_strategy import MiningStrategy
import asyncio

class VerticalSearchStrategy(MiningStrategy):
    """
    Mining strategy that mines a single vertical column from surface to target depth.
    Simple and efficient for targeted mining at a specific location.
    """
    def __init__(self, mc, agent_id, workspace, agent=None):
        """Initialize the strategy with bedrock level boundary."""
        super().__init__(mc, agent_id, workspace, agent=agent)
        self.bedrock_level = 5 
    
    def get_strategy_name(self) -> str:
        """Return the strategy name identifier."""
        return "VerticalSearch"
    
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        """Mine a single column from start position down to target depth."""
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
        """Mine blocks in a column from initial height down to target depth."""
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
