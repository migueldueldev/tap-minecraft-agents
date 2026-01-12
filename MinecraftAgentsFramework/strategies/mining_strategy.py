from abc import ABC, abstractmethod
from base_agent import AgentState
import datetime
import mcpi.block as block

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
