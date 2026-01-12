from logging_config import get_logger
from abc import ABC, abstractmethod
from base_agent import AgentState
import datetime
import mcpi.block as block

class MiningStrategy(ABC):
    """
    Abstract base class for mining strategies.
    Provides common functionality for region locking, material tracking and block mining.
    """
    def __init__(self, mc, agent_id, workspace, agent=None):
        """Initialize the strategy with Minecraft connection and workspace reference."""
        self.mc = mc
        self.agent_id = agent_id
        self.agent = agent
        self.workspace = workspace
        self.collected_materials = {}
        self.locked_regions = set()
        self.block_names = self.get_block_names()
        self.logger = get_logger(f"Strategy.{self.__class__.__name__}")
    
    @abstractmethod
    async def mine(self, requirements: dict, start_position: tuple, current_position: dict, coords: dict) -> dict:
        """Execute the mining process. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the name of this mining strategy. Must be implemented by subclasses."""
        pass
    
    def should_stop_mining(self) -> bool:
        """Check if the agent has requested to stop mining."""
        if not self.agent:
            return False
        return self.agent.should_stop or self.agent.state == AgentState.STOPPED
    
    def lock_region(self, x: int, z: int) -> bool:
        """Lock a region sector to prevent conflicts with other mining operations."""
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
        """Release all locked region sectors."""
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
        """Add collected material quantity to the internal tracking."""
        if material not in self.collected_materials:
            self.collected_materials[material] = 0
        self.collected_materials[material] += quantity
    
    def requirements_met(self, requirements: dict) -> bool:
        """Check if all required materials have been collected."""
        for material, needed in requirements.items():
            if self.collected_materials.get(material, 0) < needed:
                return False
        return True
    
    def get_material_name(self, block_id: int) -> str:
        """Get the material name for a given block ID."""
        return self.block_names.get(block_id, f"UNKNOWN_{block_id}")
    
    def get_block_names(self):
        """Build a mapping of block IDs to their names."""
        return {b.id: name for name, b in block.__dict__.items() if hasattr(b, "id")}
