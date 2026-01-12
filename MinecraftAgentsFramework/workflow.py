from typing import Optional, Callable
from functools import reduce
from utils import create_message, create_command
import datetime
import asyncio

class WorkflowConfig:
    """Configuration data for workflow execution parameters."""
    def __init__(self, params: dict):
        """Initialize configuration from parsed command parameters."""
        self.x = params.get("x")
        self.z = params.get("z")
        self.range = params.get("range", 32)
        self.template = params.get("template", "Tower")
        self.miner_strategy = params.get("miner.strategy", "vertical")
        self.miner_x = params.get("miner.x")
        self.miner_y = params.get("miner.y")
        self.miner_z = params.get("miner.z")

class WorkflowState:
    """Workflow state tracking completion flags."""
    def __init__(self, exploration_complete=False, materials_requested=False, 
                 mining_complete=False, build_complete=False, current_stage=0):
        """Initialize workflow state with default completion flags."""
        self.exploration_complete = exploration_complete
        self.materials_requested = materials_requested
        self.mining_complete = mining_complete
        self.build_complete = build_complete
        self.current_stage = current_stage

    def update(self, **updates) -> "WorkflowState":
        """Return new state with updates applied."""
        return WorkflowState(
            exploration_complete=updates.get("exploration_complete", self.exploration_complete),
            materials_requested=updates.get("materials_requested", self.materials_requested),
            mining_complete=updates.get("mining_complete", self.mining_complete),
            build_complete=updates.get("build_complete", self.build_complete),
            current_stage=updates.get("current_stage", self.current_stage),
        )

def handle_map_message(state: WorkflowState, message: dict) -> WorkflowState:
    """Handle exploration map completion message."""
    return state.update(exploration_complete=True)

def handle_requirements_message(state: WorkflowState, message: dict) -> WorkflowState:
    """Handle materials requirements publication message."""
    return state.update(materials_requested=True)

def handle_inventory_message(state: WorkflowState, message: dict) -> WorkflowState:
    """Handle mining inventory update message."""
    payload = message.get("payload", {})
    if payload.get("complete", False):
        return state.update(mining_complete=True)
    return state

def handle_build_message(state: WorkflowState, message: dict) -> WorkflowState:
    """Handle build progress update message."""
    if message.get("status") == "COMPLETED":
        return state.update(build_complete=True)
    return state

# Message type to handler mapping
MESSAGE_HANDLERS = {
    "map.v1": handle_map_message,
    "materials.requirements.v1": handle_requirements_message,
    "inventory.v1": handle_inventory_message,
    "build.v1": handle_build_message,
}

def process_message(state: WorkflowState, message: dict) -> WorkflowState:
    """Process a message and return updated state."""
    msg_type = message.get("type", "")
    handler = MESSAGE_HANDLERS.get(msg_type, lambda s, m: s)
    return handler(state, message)

def build_command(target: str, action: str, parameters: dict, stage: int) -> dict:
    """Build a command message for an agent."""
    context = {
        "task_id": str(id(asyncio.current_task())),
        "workflow_stage": stage
    }
    return create_command("Workflow", target, action, parameters, context=context)

def build_exploration_params(config: WorkflowConfig) -> dict:
    """Build exploration parameters from configuration."""
    params = {"range": config.range}
    if config.x is not None:
        params["x"] = config.x
    if config.z is not None:
        params["z"] = config.z
    return params

def build_mining_params(config: WorkflowConfig) -> dict:
    """Build mining parameters from configuration."""
    base = {"strategy": config.miner_strategy}
    optional = [("x", config.miner_x), ("y", config.miner_y), ("z", config.miner_z)]
    # Exclude empty values
    return reduce(
        lambda acc, kv: {**acc, kv[0]: kv[1]} if kv[1] is not None else acc,
        optional,
        base
    )

class Workflow:
    """
    Coordinates multi-agent workflow for terrain exploration,
    material gathering from mining activities and structure building.
    Implemented as a singleton to ensure only one workflow instance exists.
    """
    
    OBSERVABLE_MESSAGES = set({"map.v1", "materials.requirements.v1", "inventory.v1", "build.v1"})
    
    _instance: Optional["Workflow"] = None
    
    def __new__(cls, mc=None, workspace=None, agents: list = None):
        """Singleton pattern: Return existing instance or create new one."""
        if cls._instance is None:
            cls._instance = super(Workflow, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, mc, workspace, agents: list):
        """Initialize the workflow with Minecraft connection, workspace and agent references."""
        # Singleton pattern: Only initialize once
        if self._initialized:
            return
            
        self.mc = mc
        self.workspace = workspace
        self.agents = {a.__class__.__name__: a for a in agents}
        self.state = WorkflowState()
        self.config: Optional[WorkflowConfig] = None
        self.is_running = False
        self.should_stop = False
        self.message_queue = asyncio.Queue()
        
        # Register as message observer
        workspace.register_workflow_observer(self)
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> Optional["Workflow"]:
        """Get the current workflow instance, if it exists."""
        return cls._instance

    def receive_message(self, message: dict):
        """Receive message from workspace."""
        if message.get("type") in self.OBSERVABLE_MESSAGES:
            self.message_queue.put_nowait(message)
    
    async def run(self, parameters: dict):
        """Execute the full coordinated workflow."""
        if self.is_running:
            self.mc.postToChat("Workflow is already running")
            return

        self.config = WorkflowConfig(parameters)
        self._reset()
        
        self._log("WORKFLOW_STARTED", self._config_summary())
        self.mc.postToChat("Workflow has started running")

        try:
            await self._execute_stages()
            if not self.should_stop:
                self.mc.postToChat("Workflow has been completed")
                self._log("WORKFLOW_COMPLETED", {"stages": self.state.current_stage})
        except asyncio.CancelledError:
            self._log("WORKFLOW_CANCELLED", {"stage": self.state.current_stage})
            self.mc.postToChat("Workflow has been cancelled")
        except Exception as e:
            self._log("WORKFLOW_ERROR", {"error": str(e), "stage": self.state.current_stage})
            self.mc.postToChat(f"Workflow error: {e}")
        finally:
            self.is_running = False

    def stop(self):
        """Stop the running workflow."""
        self.should_stop = True
        self.mc.postToChat("Workflow stopping...")

    def help(self):
        """Display workflow help."""
        lines = [
            "Workflow help commands:",
            "  ./workflow run [x=<int> z=<int>] [range=<int>] [template=<name>]",
            "    [miner.strategy=<vertical|grid|vein>] [miner.x=<int> miner.y=<int> miner.z=<int>]",
            "  ./workflow stop",
            ""
            "Workflow stages: Exploration → Planning → Mining → Building",
        ]
        for line in lines:
            self.mc.postToChat(line)
    
    async def _execute_stages(self):
        """Execute workflow stages in sequence."""
        stages = [
            ("Exploration", self._stage_exploration, lambda: self.state.exploration_complete, 120.0),
            ("Planning", self._stage_planning, lambda: self.state.materials_requested, 30.0),
            ("Mining", self._stage_mining, lambda: self.state.mining_complete, 600.0),
            ("Building", self._stage_building, lambda: self.state.build_complete, 300.0),
        ]
        
        for name, execute, condition, timeout in stages:
            if self.should_stop:
                break
                
            self.mc.postToChat(f"[Workflow] Stage: {name}")
            self._log(f"STAGE_{name.upper()}_START", {})
            
            await execute()
            await self._wait_for(condition, timeout, name)
            
            self.state = self.state.update(current_stage=self.state.current_stage + 1)
            self._log(f"STAGE_{name.upper()}_END", {})

    async def _wait_for(self, condition: Callable[[], bool], timeout: float, stage: str):
        """Wait for condition or timeout while processing messages meanwhile."""
        start = asyncio.get_event_loop().time()
        
        while not condition():
            if self.should_stop:
                raise asyncio.CancelledError()
            
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout:
                self.mc.postToChat(f"[Workflow] {stage} stage timed out after {timeout} seconds")
                self._log("STAGE_TIMEOUT", {"stage": stage})
                break
            
            # Process pending messages
            await self._process_messages()
            await asyncio.sleep(0.5)

    async def _process_messages(self):
        """Process all pending messages from queue."""
        while not self.message_queue.empty():
            try:
                message = self.message_queue.get_nowait()
                self.state = process_message(self.state, message)
                self._log("MESSAGE_PROCESSED", {"type": message.get("type")})
            except asyncio.QueueEmpty:
                break
    
    async def _stage_exploration(self):
        """Stage 1: ExplorerBot analyzes terrain."""
        params = build_exploration_params(self.config)
        self._send_command("ExplorerBot", "start", params)
        self.mc.postToChat(f"[Workflow] Explorer scanning (x={params.get('x')} z={params.get('z')} range={params.get('range')})")

    async def _stage_planning(self):
        """Stage 2: BuilderBot loads template and publishes BOM."""
        self._send_command("BuilderBot", "plan", {"set": self.config.template})
        self.mc.postToChat(f"[Workflow] Builder planning (template={self.config.template})")

    async def _stage_mining(self):
        """Stage 3: MinerBot collects required materials."""
        params = build_mining_params(self.config)
        set_params = {"strategy": params.get("strategy")}
        self._send_command("MinerBot", "set", set_params)
        await asyncio.sleep(0.5)
        start_params = {k: v for k, v in params.items() if k != "strategy"}
        self._send_command("MinerBot", "start", start_params)
        self.mc.postToChat(f"[Workflow] Miner collecting (strategy={self.config.miner_strategy} x={self.config.miner_x} y={self.config.miner_y} z={self.config.miner_z})")

    async def _stage_building(self):
        """Stage 4: BuilderBot constructs the structure."""
        self._send_command("BuilderBot", "build", {})
        self.mc.postToChat("[Workflow] Builder constructing")
    
    def _reset(self):
        """Reset workflow state."""
        self.state = WorkflowState()
        self.is_running = True
        self.should_stop = False
        # Clear message queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _send_command(self, target: str, action: str, parameters: dict):
        """Send command to target agent."""
        command = build_command(target, action, parameters, self.state.current_stage)
        self.workspace.post_command(target, command)
        self._log("COMMAND_SENT", {"target": target, "action": action, "parameters": parameters})

    def _log(self, event: str, data: dict):
        """Log workflow event."""
        self.workspace.log_event(f"WORKFLOW_{event}", "Workflow", {"stage": self.state.current_stage, **data})

    def _config_summary(self) -> dict:
        """Return configuration as dictionary for logging."""
        return {
            "x": self.config.x, "z": self.config.z,
            "range": self.config.range, "template": self.config.template,
            "miner_strategy": self.config.miner_strategy,
            "miner_x": self.config.miner_x, "miner_y": self.config.miner_y,
            "miner_z": self.config.miner_z
        }
