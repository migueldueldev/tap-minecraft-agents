"""
Integration tests for inter-agent communication.

This module tests the message passing and communication patterns
between different agent types including:
- Builder-Miner material requirements flow
- Explorer-Builder terrain data sharing
- State change notifications
- Command routing through SharedWorkspace
"""

import pytest
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from base_agent import BaseAgent, AgentState
from shared_workspace import SharedWorkspace


class MockMinecraft:
    """Mock Minecraft connection for integration tests."""
    
    def __init__(self):
        self.chat_messages = []
        self.blocks_set = []
        self.player = MagicMock()
        self.player.getTilePos.return_value = MagicMock(x=0, y=64, z=0)
        self.events = MagicMock()
        self.events.pollChatPosts.return_value = []
    
    def postToChat(self, message):
        self.chat_messages.append(message)
    
    def setBlock(self, x, y, z, block_id, data=0):
        self.blocks_set.append((x, y, z, block_id, data))
    
    def setBlocks(self, x1, y1, z1, x2, y2, z2, block_id, data=0):
        pass
    
    def getBlock(self, x, y, z):
        return 0
    
    def getBlockWithData(self, x, y, z):
        return MagicMock(id=1, data=0)
    
    def getHeight(self, x, z):
        return 64


class SimpleSenderAgent(BaseAgent):
    """Simple agent that sends messages."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.sent_messages = []
    
    async def perceive(self, **kwargs):
        pass
    
    async def decide(self, **kwargs):
        pass
    
    async def act(self, **kwargs):
        pass
    
    def send_material_requirements(self, requirements):
        """Send material requirements message to MinerBot."""
        message = {
            "type": "materials.requirements.v1",
            "source": self.__class__.__name__,
            "target": "MinerBot",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "payload": {
                "requirements": requirements
            },
            "status": "PENDING"
        }
        self.workspace.post_message(message)
        self.sent_messages.append(message)
        return message


class SimpleReceiverAgent(BaseAgent):
    """Simple agent that receives and processes messages."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.received_requirements = {}
        self.inventory = {}
    
    async def perceive(self, **kwargs):
        messages = self.get_messages()
        for msg in messages:
            if msg.get("type") == "materials.requirements.v1":
                self.received_requirements = msg.get("payload", {}).get("requirements", {})
    
    async def decide(self, **kwargs):
        pass
    
    async def act(self, **kwargs):
        pass
    
    def send_inventory_update(self, materials, complete=False):
        """Send inventory update back to sender."""
        message = {
            "type": "inventory.v1",
            "source": self.__class__.__name__,
            "target": "BuilderBot",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "payload": {
                "materials": materials,
                "complete": complete
            },
            "status": "COMPLETED" if complete else "IN_PROGRESS"
        }
        self.workspace.post_message(message)
        return message


class TestInterAgentMessageFlow:
    """Tests for complete message flow between agents."""
    
    @pytest.fixture
    def multi_agent_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        
        # Create sender (BuilderBot equivalent)
        sender = SimpleSenderAgent(mc, workspace)
        sender.__class__ = type('BuilderBot', (SimpleSenderAgent,), {})
        
        # Create receiver (MinerBot equivalent)
        receiver = SimpleReceiverAgent(mc, workspace)
        receiver.__class__ = type('MinerBot', (SimpleReceiverAgent,), {})
        
        return sender, receiver, workspace, mc
    
    def test_material_requirements_flow(self, multi_agent_setup):
        """Test complete flow of material requirements from Builder to Miner."""
        sender, receiver, workspace, _ = multi_agent_setup
        
        requirements = {"STONE": 10, "IRON_ORE": 5, "DIAMOND_ORE": 2}
        
        # Builder sends requirements
        message = sender.send_material_requirements(requirements)
        
        # Verify message was logged
        with open(workspace.log_file, 'r') as f:
            log_content = f.read()
        assert "MESSAGE_POSTED" in log_content
        
        # Verify receiver got the message
        assert len(receiver.local_message_queue) == 1
    
    @pytest.mark.asyncio
    async def test_full_perceive_cycle_receives_message(self, multi_agent_setup):
        """Test that receiver processes message during perceive cycle."""
        sender, receiver, workspace, _ = multi_agent_setup
        
        requirements = {"STONE": 10, "IRON_ORE": 5}
        sender.send_material_requirements(requirements)
        
        # Run receiver's perceive
        await receiver.perceive()
        
        # Requirements should be stored
        assert receiver.received_requirements == requirements
    
    @pytest.mark.asyncio
    async def test_bidirectional_communication(self, multi_agent_setup):
        """Test bidirectional message flow between agents."""
        sender, receiver, workspace, _ = multi_agent_setup
        
        # Swap roles for receiving inventory updates
        sender.__class__ = type('BuilderBot', (SimpleSenderAgent,), {})
        
        # Create a receiver agent that can send back
        class TwoWayReceiver(SimpleReceiverAgent):
            async def perceive(self, **kwargs):
                await super().perceive(**kwargs)
                # Auto-respond with inventory update
                if self.received_requirements:
                    materials = [
                        {"material": m, "collected": q, "required": q, "percentage": 100}
                        for m, q in self.received_requirements.items()
                    ]
                    self.send_inventory_update(materials, complete=True)
        
        two_way = TwoWayReceiver(MockMinecraft(), workspace)
        two_way.__class__ = type('MinerBot', (TwoWayReceiver,), {})
        
        # Register new agent
        workspace.remove_observer(receiver)
        
        # Send requirements
        requirements = {"STONE": 5}
        sender.send_material_requirements(requirements)
        
        # Process on receiver
        await two_way.perceive()
        
        # Check that builder received inventory update
        assert len(sender.local_message_queue) == 1
        msg = sender.local_message_queue[0]
        assert msg["type"] == "inventory.v1"


class TestCommandRouting:
    """Tests for command routing through workspace."""
    
    @pytest.fixture
    def command_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        
        class Agent1(SimpleSenderAgent):
            pass
        
        class Agent2(SimpleSenderAgent):
            pass
        
        agent1 = Agent1(mc, workspace)
        agent2 = Agent2(mc, workspace)
        
        return agent1, agent2, workspace, mc
    
    def test_command_reaches_correct_agent(self, command_setup):
        """Test that commands are routed to the correct agent by class name."""
        agent1, agent2, workspace, _ = command_setup
        
        command = {
            "type": "command.control.v1",
            "payload": {"action": "start", "parameters": {"x": 100}}
        }
        
        workspace.post_command("Agent1", command)
        
        assert len(agent1.local_command_queue) == 1
        assert len(agent2.local_command_queue) == 0
        
        workspace.post_command("Agent2", command)
        
        assert len(agent1.local_command_queue) == 1
        assert len(agent2.local_command_queue) == 1
    
    def test_command_to_nonexistent_agent(self, command_setup):
        """Test that commands to non-existent agents don't cause errors."""
        _, _, workspace, _ = command_setup
        
        command = {"payload": {"action": "test"}}
        # Should not raise exception
        workspace.post_command("NonExistentAgent", command)


class TestStateChangeLogging:
    """Tests for state change logging through workspace."""
    
    @pytest.fixture
    def state_logging_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        
        class TestAgent(BaseAgent):
            def __init__(self, mc, workspace):
                super().__init__(mc, workspace)
            
            async def perceive(self, **kwargs):
                pass
            
            async def decide(self, **kwargs):
                pass
            
            async def act(self, **kwargs):
                pass
        
        agent = TestAgent(mc, workspace)
        agent.__class__ = type('MinerBot', (TestAgent,), {})
        
        return agent, workspace
    
    @pytest.mark.asyncio
    async def test_error_state_logs_to_workspace(self, state_logging_setup):
        """Test that ERROR state is logged through workspace."""
        agent, workspace = state_logging_setup
        
        agent.set_state(AgentState.ERROR, reason="Mining failed")
        
        # Verify that state was changed
        assert agent.state == AgentState.ERROR
        
        # Verify that logged to workspace (read log file)
        import json
        with open(workspace.log_file, 'r') as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        state_changes = [e for e in events if e["event"] == "STATE_CHANGE"]
        assert len(state_changes) > 0
        last_change = state_changes[-1]
        assert last_change["data"]["new_state"] == "ERROR"
        assert last_change["data"]["reason"] == "Mining failed"
    
    @pytest.mark.asyncio
    async def test_stop_state_logs_to_workspace(self, state_logging_setup):
        """Test that STOPPED state is logged through workspace."""
        agent, workspace = state_logging_setup
        
        agent.set_state(AgentState.STOPPED, reason="User requested stop")
        
        assert agent.state == AgentState.STOPPED
        
        import json
        with open(workspace.log_file, 'r') as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        state_changes = [e for e in events if e["event"] == "STATE_CHANGE"]
        last_change = state_changes[-1]
        assert last_change["data"]["new_state"] == "STOPPED"
    
    @pytest.mark.asyncio
    async def test_running_state_logs_to_workspace(self, state_logging_setup):
        """Test that all state changes are logged consistently."""
        agent, workspace = state_logging_setup
        
        agent.set_state(AgentState.RUNNING, reason="Started")
        
        import json
        with open(workspace.log_file, 'r') as f:
            events = [json.loads(line) for line in f if line.strip()]
        
        state_changes = [e for e in events if e["event"] == "STATE_CHANGE"]
        last_change = state_changes[-1]
        assert last_change["data"]["new_state"] == "RUNNING"


class TestMessageOrdering:
    """Tests for message ordering and sequencing."""
    
    @pytest.fixture
    def ordering_setup(self, tmp_path):
        mc = MockMinecraft()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        
        sender = SimpleSenderAgent(mc, workspace)
        sender.__class__ = type('Sender', (SimpleSenderAgent,), {})
        
        receiver = SimpleReceiverAgent(mc, workspace)
        receiver.__class__ = type('Receiver', (SimpleReceiverAgent,), {})
        
        return sender, receiver, workspace
    
    def test_messages_received_in_order(self, ordering_setup):
        """Test that messages are received in FIFO order."""
        sender, receiver, workspace = ordering_setup
        
        # Send multiple messages
        for i in range(10):
            message = {
                "type": "test.v1",
                "source": "Sender",
                "target": "Receiver",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "payload": {"sequence": i},
                "status": "SUCCESS"
            }
            workspace.post_message(message)
        
        # Verify order
        for i in range(10):
            msg = receiver.local_message_queue[i]
            assert msg["payload"]["sequence"] == i
    
    def test_get_messages_preserves_order(self, ordering_setup):
        """Test that get_messages returns messages in order."""
        sender, receiver, workspace = ordering_setup
        
        for i in range(5):
            receiver.receive_message({"seq": i})
        
        messages = receiver.get_messages()
        
        for i, msg in enumerate(messages):
            assert msg["seq"] == i


class TestWorkspacePersistence:
    """Tests for workspace logging and persistence."""
    
    @pytest.fixture
    def persistence_setup(self, tmp_path):
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "persistence_test.log")
        mc = MockMinecraft()
        
        agent = SimpleSenderAgent(mc, workspace)
        
        return agent, workspace, tmp_path
    
    def test_log_contains_all_events(self, persistence_setup):
        """Test that all events are logged to file."""
        agent, workspace, _ = persistence_setup
        
        # Generate various events
        workspace.log_event("TEST_EVENT_1", "TestAgent", {"data": 1})
        workspace.log_event("TEST_EVENT_2", "TestAgent", {"data": 2})
        workspace.post_command("SimpleSenderAgent", {"action": "test"})
        
        with open(workspace.log_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) >= 3
        
        events = [json.loads(line) for line in lines]
        event_types = [e["event"] for e in events]
        
        assert "TEST_EVENT_1" in event_types
        assert "TEST_EVENT_2" in event_types
        assert "COMMAND_POSTED" in event_types
    
    def test_final_state_save(self, persistence_setup):
        """Test that final state is properly saved."""
        agent, workspace, _ = persistence_setup
        
        agent.args = {"test_param": 123}
        
        workspace.save_final_state([agent])
        
        with open(workspace.log_file, 'r') as f:
            content = f.read()
        
        # save_final_state writes indented JSON, so parse the whole content
        # It may contain other log entries before, so find the SYSTEM_SHUTDOWN entry
        import re
        # Find the JSON object containing SYSTEM_SHUTDOWN
        # The save_final_state writes with indent=2, so it's multi-line
        assert "SYSTEM_SHUTDOWN" in content
        assert '"test_param": 123' in content or '"test_param":123' in content
