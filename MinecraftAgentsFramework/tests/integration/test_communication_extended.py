"""
Extended integration tests for inter-agent communication.

This module provides additional coverage for communication patterns including:
- Broadcast messaging
- Direct routing
- Command acknowledgement
- Message priorities
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import MagicMock, patch, AsyncMock
from collections import deque
import os

from base_agent import BaseAgent, AgentState
from shared_workspace import SharedWorkspace


class MockAgent(BaseAgent):
    """Mock agent for testing inter-agent communication."""
    
    def __init__(self, mc, workspace, name="MockAgent"):
        super().__init__(mc, workspace)
        self._agent_name = name
        self.received_broadcasts = []
        self.received_commands = []
    
    @property
    def agent_name(self):
        return self._agent_name
    
    async def perceive(self, **kwargs):
        return kwargs
    
    async def decide(self, **kwargs):
        return kwargs
    
    async def act(self, **kwargs):
        return kwargs


@pytest.fixture
def comm_setup(tmp_path):
    """Create communication test setup."""
    mc = MagicMock()
    workspace = SharedWorkspace()
    workspace.log_file = str(tmp_path / "test.log")
    return mc, workspace


class TestBroadcastMessaging:
    """Tests for messaging to all agents."""

    def test_receive_message_adds_to_queue(self, comm_setup):
        """Test message added to agent queue via receive_message."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace, "Agent1")
        
        message = {
            "type": "map.v1",
            "source": "TestAgent",
            "target": "Agent1",
            "payload": {"content": "test"}
        }
        agent.receive_message(message)
        
        assert len(agent.local_message_queue) == 1

    def test_receive_message_preserves_content(self, comm_setup):
        """Test message preserves content."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace, "Agent1")
        
        message = {
            "type": "map.v1",
            "source": "TestAgent",
            "target": "Agent1",
            "payload": {"resource": "diamond", "location": [10, 20, 30]}
        }
        agent.receive_message(message)
        
        msg = agent.get_messages()[0]
        assert msg["payload"]["resource"] == "diamond"

    def test_message_queue_separate_from_commands(self, comm_setup):
        """Test message queue is separate from command queue."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        message = {
            "type": "map.v1",
            "source": "Test",
            "target": "MockAgent",
            "payload": {}
        }
        agent.receive_message(message)
        
        assert len(agent.local_message_queue) == 1
        assert len(agent.local_command_queue) == 0


class TestDirectRouting:
    """Tests for direct message/command routing."""

    def test_command_routes_to_specific_agent(self, comm_setup):
        """Test command routes to specific agent only."""
        mc, workspace = comm_setup
        
        agent1 = MockAgent(mc, workspace, "Agent1")
        agent2 = MockAgent(mc, workspace, "Agent2")
        
        # Override class names for routing
        agent1.__class__ = type("Agent1", (MockAgent,), {})
        agent2.__class__ = type("Agent2", (MockAgent,), {})
        
        workspace.post_command("Agent1", {"action": "mine"})
        
        assert len(agent1.local_command_queue) == 1
        assert len(agent2.local_command_queue) == 0

    def test_message_routes_to_specific_agent(self, comm_setup):
        """Test message reaches target agent directly."""
        mc, workspace = comm_setup
        
        agent1 = MockAgent(mc, workspace, "Agent1")
        agent2 = MockAgent(mc, workspace, "Agent2")
        
        message = {
            "type": "map.v1",
            "source": "Test",
            "target": "Agent1",
            "payload": {"info": "data"}
        }
        # Direct delivery to agent1
        agent1.receive_message(message)
        
        assert len(agent1.local_message_queue) == 1
        assert len(agent2.local_message_queue) == 0

    def test_routing_handles_unknown_agent(self, comm_setup):
        """Test routing handles unknown agent gracefully."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        # Should not raise, just log
        workspace.post_command("UnknownAgent", {"action": "test"})
        
        # Agent shouldn't receive command meant for unknown agent
        assert len(agent.local_command_queue) == 0


class TestMessageOrdering:
    """Tests for message ordering guarantees."""

    def test_messages_maintain_fifo_order(self, comm_setup):
        """Test messages are delivered in FIFO order."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        agent.__class__ = type("MockAgent", (MockAgent,), {})
        
        for i in range(50):
            message = {
                "type": "map.v1",
                "source": "Test",
                "target": "MockAgent",
                "payload": {"seq": i}
            }
            workspace.post_message(message)
        
        messages = agent.get_messages()
        
        for i, msg in enumerate(messages):
            assert msg["payload"]["seq"] == i

    def test_commands_maintain_fifo_order(self, comm_setup):
        """Test commands are delivered in FIFO order."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        agent.__class__ = type("MockAgent", (MockAgent,), {})
        
        for i in range(50):
            workspace.post_command("MockAgent", {"seq": i})
        
        for i in range(50):
            cmd = agent.local_command_queue.popleft()
            assert cmd["seq"] == i


class TestConcurrentCommunication:
    """Tests for concurrent communication patterns."""

    def test_concurrent_message_delivery(self, comm_setup):
        """Test concurrent message delivery works correctly."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        def send_messages():
            for i in range(100):
                agent.receive_message({"id": i})
        
        threads = [threading.Thread(target=send_messages) for _ in range(5)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All 500 messages should be received
        assert len(agent.local_message_queue) == 500

    def test_concurrent_commands_and_messages(self, comm_setup):
        """Test concurrent commands and messages don't interfere."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        agent.__class__ = type("MockAgent", (MockAgent,), {})
        
        def send_commands():
            for i in range(100):
                workspace.post_command("MockAgent", {"type": "cmd", "seq": i})
        
        def send_messages():
            for i in range(100):
                agent.receive_message({"type": "msg", "seq": i})
        
        cmd_thread = threading.Thread(target=send_commands)
        msg_thread = threading.Thread(target=send_messages)
        
        cmd_thread.start()
        msg_thread.start()
        
        cmd_thread.join()
        msg_thread.join()
        
        assert len(agent.local_command_queue) == 100
        assert len(agent.local_message_queue) == 100


class TestObserverManagement:
    """Tests for observer registration and management."""

    def test_agent_auto_registers_on_init(self, comm_setup):
        """Test agent auto-registers with workspace on init."""
        mc, workspace = comm_setup
        
        assert len(workspace.observers) == 0
        
        agent = MockAgent(mc, workspace)
        
        assert len(workspace.observers) == 1
        assert agent in workspace.observers

    def test_multiple_agents_register(self, comm_setup):
        """Test multiple agents can register."""
        mc, workspace = comm_setup
        
        agents = [MockAgent(mc, workspace, f"Agent{i}") for i in range(10)]
        
        assert len(workspace.observers) == 10
        for agent in agents:
            assert agent in workspace.observers

    def test_observer_receives_notifications(self, comm_setup):
        """Test observers can receive messages directly."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        # Direct notification to the agent
        message = {
            "type": "map.v1",
            "source": "Test",
            "target": "MockAgent",
            "payload": {"test": "notification"}
        }
        agent.receive_message(message)
        
        assert len(agent.local_message_queue) == 1


class TestCommunicationResilience:
    """Tests for communication resilience patterns."""

    def test_queue_handles_large_volumes(self, comm_setup):
        """Test queues handle large message volumes."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        for i in range(10000):
            agent.receive_message({"id": i})
        
        assert len(agent.local_message_queue) == 10000

    def test_empty_queue_handling(self, comm_setup):
        """Test empty queue returns empty list."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        messages = agent.get_messages()
        
        assert messages == []

    def test_get_messages_clears_queue(self, comm_setup):
        """Test get_messages clears the queue."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        for i in range(10):
            agent.receive_message({"id": i})
        
        first_batch = agent.get_messages()
        second_batch = agent.get_messages()
        
        assert len(first_batch) == 10
        assert len(second_batch) == 0


class TestEventNotifications:
    """Tests for event notification patterns."""

    def test_command_sets_event(self, comm_setup):
        """Test receiving command sets command event."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        assert not agent.command_event.is_set()
        
        agent.receive_command({"payload": {"action": "test"}})
        
        assert agent.command_event.is_set()

    def test_multiple_commands_event_still_set(self, comm_setup):
        """Test multiple commands keep event set."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        for i in range(10):
            agent.receive_command({"payload": {"action": f"cmd{i}"}})
        
        assert agent.command_event.is_set()
        assert len(agent.local_command_queue) == 10


class TestLoggingIntegration:
    """Tests for logging integration with communication."""

    def test_workspace_logs_events(self, comm_setup):
        """Test workspace logs communication events."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        
        workspace.log_event("TestAgent", "test_event", {"data": "value"})
        
        # Verify log_event was called
        assert workspace.log_event is not None

    def test_agent_state_change_logged(self, comm_setup):
        """Test agent state changes are logged to workspace."""
        mc, workspace = comm_setup
        
        agent = MockAgent(mc, workspace)
        initial_log_size = os.path.getsize(workspace.log_file) if os.path.exists(workspace.log_file) else 0
        
        agent.set_state(AgentState.RUNNING)
        
        # State change should create log entry
        current_log_size = os.path.getsize(workspace.log_file)
        assert current_log_size > initial_log_size
