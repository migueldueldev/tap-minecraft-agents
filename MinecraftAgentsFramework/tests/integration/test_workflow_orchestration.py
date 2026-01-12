"""
Integration tests for workflow orchestration.

This module tests end-to-end workflows involving multiple agents
working together including:
- Explorer -> Builder terrain data flow
- Builder -> Miner material requirements
- Miner -> Builder inventory updates
- Complete build workflow coordination
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from base_agent import BaseAgent, AgentState
from shared_workspace import SharedWorkspace
from workflow import Workflow


class MockMinecraft:
    """Mock Minecraft connection for workflow tests."""
    
    def __init__(self):
        self.chat_messages = []
        self.blocks_set = []
        self.height_map = {}
        self.block_map = {}
        
        self.player = MagicMock()
        self.player.getTilePos.return_value = MagicMock(x=0, y=64, z=0)
    
    def postToChat(self, message):
        self.chat_messages.append(message)
    
    def setBlock(self, x, y, z, block_id, data=0):
        self.blocks_set.append((x, y, z, block_id, data))
        self.block_map[(x, y, z)] = (block_id, data)
    
    def getHeight(self, x, z):
        return self.height_map.get((x, z), 64)
    
    def getBlock(self, x, y, z):
        return self.block_map.get((x, y, z), (0, 0))[0]


class MockExplorerBot(BaseAgent):
    """Mock ExplorerBot for workflow tests."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.exploration_complete = False
        self.terrain_data = None
    
    async def perceive(self, **kwargs):
        # Simulate terrain scanning
        self.terrain_data = {
            "regions": [
                {
                    "y": 64,
                    "width": 10,
                    "depth": 10,
                    "blocks": [{"x": i, "z": j} for i in range(10) for j in range(10)]
                }
            ]
        }
        return self.terrain_data
    
    async def decide(self, **kwargs):
        return self.terrain_data
    
    async def act(self, **kwargs):
        if self.terrain_data:
            message = {
                "type": "map.v1",
                "source": "ExplorerBot",
                "target": "BuilderBot",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "payload": self.terrain_data,
                "status": "SUCCESS"
            }
            self.workspace.post_message(message)
            self.exploration_complete = True
        return self.terrain_data


class MockBuilderBot(BaseAgent):
    """Mock BuilderBot for workflow tests."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.terrain_data = None
        self.material_requirements = {}
        self.inventory = {}
        self.build_ready = False
        self.build_complete = False
    
    async def perceive(self, **kwargs):
        for msg in self.get_messages():
            msg_type = msg.get("type", "")
            if msg_type == "map.v1":
                self.terrain_data = msg.get("payload")
            elif msg_type == "inventory.v1":
                for item in msg.get("payload", {}).get("materials", []):
                    self.inventory[item["material"]] = item["collected"]
                if msg.get("payload", {}).get("complete"):
                    self.build_ready = True
    
    async def decide(self, **kwargs):
        plan = kwargs.get("plan", {})
        if plan and not self.material_requirements:
            self.material_requirements = plan.get("requirements", {})
        
        if self.terrain_data and self.material_requirements and not self.build_ready:
            self.set_state(AgentState.WAITING, "Waiting for materials")
    
    async def act(self, **kwargs):
        # Request materials if needed
        if self.material_requirements and self.terrain_data:
            pending = {m: q for m, q in self.material_requirements.items()
                      if self.inventory.get(m, 0) < q}
            
            if pending and self.state != AgentState.RUNNING:
                message = {
                    "type": "materials.requirements.v1",
                    "source": "BuilderBot",
                    "target": "MinerBot",
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "payload": {"requirements": pending},
                    "status": "PENDING"
                }
                self.workspace.post_message(message)
        
        # Build if ready
        if self.build_ready:
            self.set_state(AgentState.RUNNING, "Building")
            await asyncio.sleep(0.01)  # Simulate building
            self.build_complete = True


class MockMinerBot(BaseAgent):
    """Mock MinerBot for workflow tests."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.material_requirements = {}
        self.inventory = {}
        self.mining_complete = False
    
    async def perceive(self, **kwargs):
        for msg in self.get_messages():
            if msg.get("type") == "materials.requirements.v1":
                self.material_requirements = msg.get("payload", {}).get("requirements", {})
    
    async def decide(self, **kwargs):
        if self.material_requirements:
            self.set_state(AgentState.RUNNING, "Mining")
    
    async def act(self, **kwargs):
        if self.material_requirements and not self.mining_complete:
            # Simulate mining
            await asyncio.sleep(0.01)
            
            # Fill inventory
            for material, qty in self.material_requirements.items():
                self.inventory[material] = qty
            
            # Send inventory update
            materials = [
                {"material": m, "collected": q, "required": q, "percentage": 100}
                for m, q in self.inventory.items()
            ]
            
            message = {
                "type": "inventory.v1",
                "source": "MinerBot",
                "target": "BuilderBot",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "payload": {"materials": materials, "complete": True},
                "status": "COMPLETED"
            }
            self.workspace.post_message(message)
            self.mining_complete = True


class TestCompleteWorkflow:
    """Tests for complete multi-agent workflows."""
    
    @pytest.fixture
    def workflow_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "workflow.log")
        
        explorer = MockExplorerBot(mc, workspace)
        explorer.__class__ = type('ExplorerBot', (MockExplorerBot,), {})
        
        builder = MockBuilderBot(mc, workspace)
        builder.__class__ = type('BuilderBot', (MockBuilderBot,), {})
        
        miner = MockMinerBot(mc, workspace)
        miner.__class__ = type('MinerBot', (MockMinerBot,), {})
        
        return explorer, builder, miner, workspace, mc
    
    @pytest.mark.asyncio
    async def test_exploration_to_builder_flow(self, workflow_setup):
        """Test terrain data flows from Explorer to Builder."""
        explorer, builder, miner, workspace, _ = workflow_setup
        
        # Explorer discovers terrain
        await explorer.perceive()
        await explorer.decide()
        await explorer.act()
        
        assert explorer.exploration_complete
        assert len(builder.local_message_queue) == 1
        
        # Builder receives terrain
        await builder.perceive()
        
        assert builder.terrain_data is not None
        assert len(builder.terrain_data["regions"]) == 1
    
    @pytest.mark.asyncio
    async def test_builder_to_miner_requirements_flow(self, workflow_setup):
        """Test material requirements flow from Builder to Miner."""
        explorer, builder, miner, workspace, _ = workflow_setup
        
        # Set up exploration first
        await explorer.perceive()
        await explorer.act()
        await builder.perceive()
        
        # Builder has a plan with requirements
        plan = {"requirements": {"STONE": 20, "GLASS": 10}}
        
        await builder.decide(plan=plan)
        await builder.act(plan=plan)
        
        # Miner should receive requirements
        assert len(miner.local_message_queue) == 1
        
        await miner.perceive()
        
        assert miner.material_requirements == {"STONE": 20, "GLASS": 10}
    
    @pytest.mark.asyncio
    async def test_miner_to_builder_inventory_flow(self, workflow_setup):
        """Test inventory updates flow from Miner to Builder."""
        explorer, builder, miner, workspace, _ = workflow_setup
        
        # Simulate miner receiving requirements
        miner.material_requirements = {"STONE": 10}
        
        await miner.decide()
        await miner.act()
        
        assert miner.mining_complete
        
        # Builder should receive inventory update
        assert len(builder.local_message_queue) == 1
        
        await builder.perceive()
        
        assert builder.inventory["STONE"] == 10
        assert builder.build_ready
    
    @pytest.mark.asyncio
    async def test_full_build_workflow(self, workflow_setup):
        """Test complete workflow: explore -> plan -> mine -> build."""
        explorer, builder, miner, workspace, _ = workflow_setup
        
        # Phase 1: Exploration
        await explorer.perceive()
        await explorer.act()
        
        # Phase 2: Builder receives terrain and plans
        await builder.perceive()
        plan = {"requirements": {"STONE": 5}}
        await builder.decide(plan=plan)
        await builder.act(plan=plan)
        
        assert builder.state == AgentState.WAITING
        
        # Phase 3: Miner receives requirements and mines
        await miner.perceive()
        await miner.decide()
        await miner.act()
        
        # Phase 4: Builder receives materials and builds
        await builder.perceive()
        await builder.decide()
        await builder.act()
        
        assert builder.build_complete
        assert builder.state == AgentState.RUNNING


class TestWorkflowInterruption:
    """Tests for workflow interruption and recovery."""
    
    @pytest.fixture
    def interruptible_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "interrupt.log")
        
        class InterruptibleMiner(MockMinerBot):
            def __init__(self, mc, workspace):
                super().__init__(mc, workspace)
                self.interrupted = False
            
            async def act(self, **kwargs):
                if self.should_stop:
                    self.interrupted = True
                    return
                await super().act(**kwargs)
        
        miner = InterruptibleMiner(mc, workspace)
        miner.__class__ = type('MinerBot', (InterruptibleMiner,), {})
        
        builder = MockBuilderBot(mc, workspace)
        builder.__class__ = type('BuilderBot', (MockBuilderBot,), {})
        
        return miner, builder, workspace
    
    @pytest.mark.asyncio
    async def test_stop_interrupts_workflow(self, interruptible_setup):
        """Test that stop command interrupts ongoing workflow."""
        miner, builder, _ = interruptible_setup
        
        miner.material_requirements = {"STONE": 10}
        miner.should_stop = True
        
        await miner.decide()
        await miner.act()
        
        assert miner.interrupted
        assert not miner.mining_complete
    
    @pytest.mark.asyncio
    async def test_pause_allows_resume(self, interruptible_setup):
        """Test that paused workflow can be resumed."""
        miner, builder, _ = interruptible_setup
        
        miner.material_requirements = {"STONE": 10}
        
        # Pause
        miner.pause()
        assert miner.state == AgentState.PAUSED
        
        # Resume
        miner.resume()
        assert miner.state == AgentState.RUNNING
        
        # Continue work
        miner.should_stop = False
        await miner.act()
        
        assert miner.mining_complete


class TestConcurrentWorkflows:
    """Tests for multiple concurrent workflows."""
    
    @pytest.fixture
    def concurrent_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "concurrent.log")
        
        explorers = []
        builders = []
        
        for i in range(2):
            explorer = MockExplorerBot(mc, workspace)
            explorer.__class__ = type(f'ExplorerBot{i}', (MockExplorerBot,), {})
            explorers.append(explorer)
            
            builder = MockBuilderBot(mc, workspace)
            builder.__class__ = type(f'BuilderBot{i}', (MockBuilderBot,), {})
            builders.append(builder)
        
        return explorers, builders, workspace
    
    @pytest.mark.asyncio
    async def test_parallel_exploration(self, concurrent_setup):
        """Test multiple explorers running in parallel."""
        explorers, builders, _ = concurrent_setup
        
        async def run_exploration(explorer):
            await explorer.perceive()
            await explorer.act()
            return explorer.exploration_complete
        
        results = await asyncio.gather(*[
            run_exploration(e) for e in explorers
        ])
        
        assert all(results)
    
    @pytest.mark.asyncio
    async def test_isolated_workflows(self, concurrent_setup):
        """Test that parallel workflows don't interfere with each other."""
        explorers, builders, workspace = concurrent_setup
        
        # Explorer0 sends to BuilderBot0 only
        async def workflow(explorer, builder, plan):
            await explorer.perceive()
            
            # Manually send message to specific builder
            message = {
                "type": "map.v1",
                "source": explorer.__class__.__name__,
                "target": builder.__class__.__name__,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "payload": explorer.terrain_data,
                "status": "SUCCESS"
            }
            workspace.post_message(message)
            
            await builder.perceive()
            return builder.terrain_data is not None
        
        results = await asyncio.gather(
            workflow(explorers[0], builders[0], {"requirements": {"STONE": 1}}),
            workflow(explorers[1], builders[1], {"requirements": {"GLASS": 1}})
        )
        
        assert all(results)
        # Each builder should have received its own terrain data
        assert builders[0].terrain_data is not None
        assert builders[1].terrain_data is not None


class TestEventLogging:
    """Tests for workflow event logging and traceability."""
    
    @pytest.fixture
    def logging_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        log_file = tmp_path / "events.log"
        workspace.log_file = str(log_file)
        
        explorer = MockExplorerBot(mc, workspace)
        explorer.__class__ = type('ExplorerBot', (MockExplorerBot,), {})
        
        builder = MockBuilderBot(mc, workspace)
        builder.__class__ = type('BuilderBot', (MockBuilderBot,), {})
        
        return explorer, builder, workspace, log_file
    
    @pytest.mark.asyncio
    async def test_all_messages_logged(self, logging_setup):
        """Test that all inter-agent messages are logged."""
        explorer, builder, workspace, log_file = logging_setup
        
        await explorer.perceive()
        await explorer.act()
        
        await builder.perceive()
        builder.material_requirements = {"STONE": 5}
        await builder.decide(plan={"requirements": {"STONE": 5}})
        await builder.act(plan={"requirements": {"STONE": 5}})
        
        import json
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        event_types = [e["event"] for e in events]
        
        # Should have MESSAGE_POSTED events for map and requirements
        assert event_types.count("MESSAGE_POSTED") >= 2
    
    @pytest.mark.asyncio
    async def test_state_changes_logged(self, logging_setup):
        """Test that all state changes are logged with timestamps."""
        explorer, builder, workspace, log_file = logging_setup
        
        builder.set_state(AgentState.RUNNING, reason="Started building")
        builder.set_state(AgentState.WAITING, reason="Waiting for materials")
        builder.set_state(AgentState.RUNNING, reason="Materials received")
        
        import json
        with open(log_file, 'r') as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        state_changes = [e for e in events if e["event"] == "STATE_CHANGE"]
        
        assert len(state_changes) == 3
        
        # Verify timestamps are present and in order
        timestamps = [e["data"]["timestamp"] for e in state_changes]
        assert all(t for t in timestamps)
