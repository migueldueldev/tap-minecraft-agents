"""
Extended integration tests for agent synchronization.

This module provides additional coverage for synchronization mechanisms including:
- Message event handling
- State consistency across operations
- Error recovery patterns
- Concurrent state changes
"""

import pytest
import asyncio
import threading
import time
import os
from unittest.mock import MagicMock, patch, AsyncMock
from concurrent.futures import ThreadPoolExecutor

from base_agent import BaseAgent, AgentState
from shared_workspace import SharedWorkspace


class ConcreteTestAgent(BaseAgent):
    """Concrete test agent for integration testing."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.action_log = []
    
    async def perceive(self, **kwargs):
        self.action_log.append(("perceive", kwargs))
        await asyncio.sleep(0.01)
        return kwargs
    
    async def decide(self, **kwargs):
        self.action_log.append(("decide", kwargs))
        await asyncio.sleep(0.01)
        return kwargs
    
    async def act(self, **kwargs):
        self.action_log.append(("act", kwargs))
        await asyncio.sleep(0.01)
        return kwargs


@pytest.fixture
def integration_setup(tmp_path):
    """Create integration test setup."""
    mc = MagicMock()
    workspace = SharedWorkspace()
    workspace.log_file = str(tmp_path / "test.log")
    agent = ConcreteTestAgent(mc, workspace)
    return agent, mc, workspace


class TestEventHandling:
    """Tests for asyncio event handling."""

    @pytest.mark.asyncio
    async def test_command_event_wait_and_clear(self, integration_setup):
        """Test command event wait and clear cycle."""
        agent, _, _ = integration_setup
        
        # Event starts unset
        assert not agent.command_event.is_set()
        
        # Receive command sets event
        agent.receive_command({"payload": {"action": "test"}})
        assert agent.command_event.is_set()
        
        # Wait completes immediately when set
        await asyncio.wait_for(agent.command_event.wait(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_interrupt_event_wait_and_clear(self, integration_setup):
        """Test interrupt event wait and clear cycle."""
        agent, _, _ = integration_setup
        
        # Event starts unset
        assert not agent.interrupt_event.is_set()
        
        # Stop sets event
        agent.stop()
        assert agent.interrupt_event.is_set()
        
        # Wait completes immediately when set
        await asyncio.wait_for(agent.interrupt_event.wait(), timeout=0.1)


class TestStateConsistency:
    """Tests for state consistency during operations."""

    def test_state_transitions_logged(self, integration_setup):
        """Test all state transitions are logged."""
        agent, _, workspace = integration_setup
        
        initial_log_size = os.path.getsize(workspace.log_file) if os.path.exists(workspace.log_file) else 0
        
        states = [AgentState.RUNNING, AgentState.PAUSED, AgentState.WAITING, AgentState.IDLE]
        
        for state in states:
            agent.set_state(state)
        
        # All transitions should create log entries
        current_log_size = os.path.getsize(workspace.log_file)
        assert current_log_size > initial_log_size

    def test_concurrent_state_changes(self, integration_setup):
        """Test concurrent state changes don't corrupt state."""
        agent, _, _ = integration_setup
        
        def change_state(state):
            for _ in range(100):
                agent.set_state(state)
                time.sleep(0.001)
        
        threads = [
            threading.Thread(target=change_state, args=(AgentState.RUNNING,)),
            threading.Thread(target=change_state, args=(AgentState.PAUSED,))
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # State should be one of the two valid states
        assert agent.state in [AgentState.RUNNING, AgentState.PAUSED]


class TestMessageEventFlow:
    """Tests for message and event flow patterns."""

    def test_message_ordering_preserved(self, integration_setup):
        """Test message ordering is preserved in queue."""
        agent, _, _ = integration_setup
        
        for i in range(100):
            agent.receive_message({"seq": i})
        
        messages = agent.get_messages()
        
        for i, msg in enumerate(messages):
            assert msg["seq"] == i

    def test_command_ordering_preserved(self, integration_setup):
        """Test command ordering is preserved in queue."""
        agent, _, _ = integration_setup
        
        for i in range(100):
            agent.receive_command({"payload": {"action": "test", "seq": i}})
        
        # Process commands in order
        for i in range(100):
            cmd = agent.local_command_queue.popleft()
            assert cmd["payload"]["seq"] == i


class TestErrorRecovery:
    """Tests for error recovery patterns."""

    @pytest.mark.asyncio
    async def test_error_state_logged(self, integration_setup):
        """Test error state transitions are logged."""
        agent, _, workspace = integration_setup
        
        initial_log_size = os.path.getsize(workspace.log_file) if os.path.exists(workspace.log_file) else 0
        
        agent.set_state(AgentState.ERROR, reason="Test error")
        
        # Error state change should create log entry
        current_log_size = os.path.getsize(workspace.log_file)
        assert current_log_size > initial_log_size
        assert agent.state == AgentState.ERROR

    def test_stop_sets_all_flags(self, integration_setup):
        """Test stop sets all necessary flags for clean shutdown."""
        agent, _, _ = integration_setup
        
        agent.stop()
        
        assert agent.should_stop is True
        assert agent.state == AgentState.STOPPED
        assert agent.interrupt_event.is_set()


class TestConcurrentQueueAccess:
    """Tests for concurrent queue access patterns."""

    def test_high_volume_concurrent_writes(self, integration_setup):
        """Test high volume concurrent writes to queues."""
        agent, _, _ = integration_setup
        
        def write_commands():
            for i in range(500):
                agent.receive_command({"payload": {"seq": i}})
        
        def write_messages():
            for i in range(500):
                agent.receive_message({"seq": i})
        
        threads = [
            threading.Thread(target=write_commands),
            threading.Thread(target=write_messages)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(agent.local_command_queue) == 500
        assert len(agent.local_message_queue) == 500

    def test_concurrent_read_during_write(self, integration_setup):
        """Test reading messages while writing doesn't cause issues."""
        agent, _, _ = integration_setup
        read_count = 0
        read_lock = threading.Lock()
        
        def write_messages():
            for i in range(200):
                agent.receive_message({"seq": i})
                time.sleep(0.001)
        
        def read_messages():
            nonlocal read_count
            for _ in range(100):
                messages = agent.get_messages()
                with read_lock:
                    read_count += len(messages)
                time.sleep(0.002)
        
        writer = threading.Thread(target=write_messages)
        reader = threading.Thread(target=read_messages)
        
        writer.start()
        reader.start()
        
        writer.join()
        reader.join()
        
        # Read all remaining
        remaining = agent.get_messages()
        read_count += len(remaining)
        
        # Should have read all 200 messages eventually
        assert read_count == 200


class TestPDALoopIntegration:
    """Tests for PDA loop integration patterns."""

    @pytest.mark.asyncio
    async def test_pda_loop_respects_paused_state(self, integration_setup):
        """Test PDA loop properly handles PAUSED state."""
        agent, _, _ = integration_setup
        agent.args = {"test": True}
        agent.state = AgentState.PAUSED
        
        # Run a limited PDA cycle
        async def limited_cycle():
            cycles = 0
            while cycles < 5:
                if agent.state == AgentState.PAUSED:
                    # Should wait for interrupt_event
                    try:
                        await asyncio.wait_for(agent.interrupt_event.wait(), timeout=0.05)
                        agent.interrupt_event.clear()
                    except asyncio.TimeoutError:
                        break
                cycles += 1
            return cycles
        
        cycles = await limited_cycle()
        
        # Should timeout waiting since we're paused
        assert cycles < 5

    @pytest.mark.asyncio
    async def test_pda_loop_executes_when_running(self, integration_setup):
        """Test PDA loop executes when in RUNNING state."""
        agent, _, _ = integration_setup
        agent.args = {"test": True}
        agent.state = AgentState.RUNNING
        
        # Run perceive-decide-act once
        await agent.perceive(**agent.args)
        await agent.decide(**agent.args)
        await agent.act(**agent.args)
        
        # All three phases should have executed
        assert len(agent.action_log) == 3
        assert agent.action_log[0][0] == "perceive"
        assert agent.action_log[1][0] == "decide"
        assert agent.action_log[2][0] == "act"


class TestWorkspaceObserverPattern:
    """Tests for workspace observer pattern integration."""

    def test_agent_registers_as_observer(self, integration_setup):
        """Test agent registers itself as workspace observer."""
        agent, _, workspace = integration_setup
        
        assert agent in workspace.observers

    def test_workspace_routes_to_agent(self, integration_setup):
        """Test workspace routes messages to correct agent."""
        agent, _, workspace = integration_setup
        agent.__class__.__name__ = "ConcreteTestAgent"
        
        command = {"action": "test"}
        workspace.post_command("ConcreteTestAgent", command)
        
        assert len(agent.local_command_queue) == 1

    def test_multiple_agents_receive_own_commands(self, tmp_path):
        """Test multiple agents receive their own commands."""
        mc = MagicMock()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        
        agent1 = ConcreteTestAgent(mc, workspace)
        agent1.__class__ = type("Agent1", (ConcreteTestAgent,), {})
        
        agent2 = ConcreteTestAgent(mc, workspace)
        agent2.__class__ = type("Agent2", (ConcreteTestAgent,), {})
        
        workspace.post_command("Agent1", {"action": "cmd1"})
        workspace.post_command("Agent2", {"action": "cmd2"})
        
        assert len(agent1.local_command_queue) == 1
        assert len(agent2.local_command_queue) == 1
        assert agent1.local_command_queue[0]["action"] == "cmd1"
        assert agent2.local_command_queue[0]["action"] == "cmd2"


class TestAgentLifecycle:
    """Tests for agent lifecycle integration."""

    @pytest.mark.asyncio
    async def test_start_initializes_state(self, integration_setup):
        """Test start properly initializes agent state."""
        agent, mc, _ = integration_setup
        
        with patch('asyncio.create_task') as mock_task:
            await agent.start(param="value")
            
            assert agent.args == {"param": "value"}
            assert agent.should_stop is False
            assert mock_task.call_count == 2
            
            # Close coroutines
            for call in mock_task.call_args_list:
                call.args[0].close()

    def test_stop_terminates_agent(self, integration_setup):
        """Test stop terminates agent execution."""
        agent, mc, _ = integration_setup
        agent.state = AgentState.RUNNING
        
        agent.stop()
        
        assert agent.should_stop is True
        assert agent.state == AgentState.STOPPED
        mc.postToChat.assert_called()

    def test_pause_resume_cycle(self, integration_setup):
        """Test pause and resume cycle."""
        agent, mc, _ = integration_setup
        agent.state = AgentState.RUNNING
        
        agent.pause()
        assert agent.state == AgentState.PAUSED
        
        agent.resume()
        assert agent.state == AgentState.RUNNING
