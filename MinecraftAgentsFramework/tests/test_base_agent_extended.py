"""
Additional unit tests for BaseAgent module.

This module provides comprehensive coverage for BaseAgent functionality including:
- State management edge cases
- Command processing variations
- Message queue handling
- PDA cycle behavior
- Error handling scenarios
"""

import pytest
import asyncio
import threading
from unittest.mock import MagicMock, patch, AsyncMock
from base_agent import BaseAgent, AgentState


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.perceive_calls = 0
        self.decide_calls = 0
        self.act_calls = 0
        self.perceive_result = None
        self.decide_result = None
        self.act_result = None
    
    async def perceive(self, **kwargs):
        self.perceive_calls += 1
        self.perceive_result = kwargs
        return kwargs
    
    async def decide(self, **kwargs):
        self.decide_calls += 1
        self.decide_result = kwargs
        return kwargs
    
    async def act(self, **kwargs):
        self.act_calls += 1
        self.act_result = kwargs
        return kwargs


@pytest.fixture
def concrete_agent_setup():
    """Create a concrete agent with mocked dependencies."""
    mc = MagicMock()
    workspace = MagicMock()
    agent = ConcreteAgent(mc, workspace)
    return agent, mc, workspace


class TestAgentStateManagement:
    """Tests for agent state management functionality."""

    def test_initial_state_is_idle(self, concrete_agent_setup):
        """Test that new agents start in IDLE state."""
        agent, _, _ = concrete_agent_setup
        assert agent.state == AgentState.IDLE

    def test_set_state_updates_state(self, concrete_agent_setup):
        """Test that set_state updates the agent state."""
        agent, _, workspace = concrete_agent_setup
        
        agent.set_state(AgentState.RUNNING, reason="Test reason")
        
        assert agent.state == AgentState.RUNNING
        workspace.log_event.assert_called()

    def test_set_state_logs_transition(self, concrete_agent_setup):
        """Test that state transition is logged with previous and new state."""
        agent, _, workspace = concrete_agent_setup
        
        agent.set_state(AgentState.RUNNING, reason="Starting")
        
        call_args = workspace.log_event.call_args
        assert call_args[0][0] == "STATE_CHANGE"
        assert call_args[0][2]["previous_state"] == "IDLE"
        assert call_args[0][2]["new_state"] == "RUNNING"
        assert call_args[0][2]["reason"] == "Starting"

    def test_set_state_without_reason(self, concrete_agent_setup):
        """Test that set_state works without providing a reason."""
        agent, _, workspace = concrete_agent_setup
        
        agent.set_state(AgentState.PAUSED)
        
        call_args = workspace.log_event.call_args
        assert "reason" not in call_args[0][2] or call_args[0][2].get("reason") is None

    def test_get_state_returns_current_state(self, concrete_agent_setup):
        """Test that get_state returns the current state."""
        agent, _, _ = concrete_agent_setup
        
        agent.state = AgentState.ERROR
        
        assert agent.get_state() == AgentState.ERROR

    def test_all_state_transitions(self, concrete_agent_setup):
        """Test transitioning through all possible states."""
        agent, _, _ = concrete_agent_setup
        
        states = [AgentState.IDLE, AgentState.RUNNING, AgentState.PAUSED, 
                  AgentState.WAITING, AgentState.ERROR, AgentState.STOPPED]
        
        for state in states:
            agent.set_state(state)
            assert agent.state == state


class TestCommandHandling:
    """Tests for command handling functionality."""

    def test_handle_command_start_sets_running(self, concrete_agent_setup):
        """Test that start command sets agent to RUNNING state."""
        agent, _, _ = concrete_agent_setup
        
        command = {"payload": {"action": "start", "parameters": {"x": 10}}}
        result = agent.handle_command(command)
        
        assert result is True
        assert agent.state == AgentState.RUNNING
        assert agent.args == {"x": 10}

    def test_handle_command_stop(self, concrete_agent_setup):
        """Test that stop command stops the agent."""
        agent, mc, _ = concrete_agent_setup
        
        command = {"payload": {"action": "stop"}}
        result = agent.handle_command(command)
        
        assert result is True
        assert agent.should_stop is True
        assert agent.state == AgentState.STOPPED

    def test_handle_command_pause(self, concrete_agent_setup):
        """Test that pause command pauses the agent."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.RUNNING
        
        command = {"payload": {"action": "pause"}}
        result = agent.handle_command(command)
        
        assert result is True
        assert agent.state == AgentState.PAUSED

    def test_handle_command_resume(self, concrete_agent_setup):
        """Test that resume command resumes a paused agent."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.PAUSED
        
        command = {"payload": {"action": "resume"}}
        result = agent.handle_command(command)
        
        assert result is True
        assert agent.state == AgentState.RUNNING

    def test_handle_command_status(self, concrete_agent_setup):
        """Test that status command posts status to chat."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.RUNNING
        
        command = {"payload": {"action": "status"}}
        result = agent.handle_command(command)
        
        assert result is True
        mc.postToChat.assert_called()

    def test_handle_command_help(self, concrete_agent_setup):
        """Test that help command displays help text."""
        agent, mc, _ = concrete_agent_setup
        
        command = {"payload": {"action": "help"}}
        result = agent.handle_command(command)
        
        assert result is True
        assert mc.postToChat.call_count >= 1

    def test_handle_command_unknown_action(self, concrete_agent_setup):
        """Test that unknown action returns False."""
        agent, _, _ = concrete_agent_setup
        
        command = {"payload": {"action": "unknown_action"}}
        result = agent.handle_command(command)
        
        assert result is False

    def test_handle_command_when_stopped(self, concrete_agent_setup):
        """Test that commands are ignored when agent is stopped (except status/help)."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.STOPPED
        
        command = {"payload": {"action": "start"}}
        result = agent.handle_command(command)
        
        assert result is False
        mc.postToChat.assert_called()

    def test_handle_command_status_when_stopped(self, concrete_agent_setup):
        """Test that status command works even when stopped."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.STOPPED
        
        command = {"payload": {"action": "status"}}
        result = agent.handle_command(command)
        
        assert result is True

    def test_handle_command_help_when_stopped(self, concrete_agent_setup):
        """Test that help command works even when stopped."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.STOPPED
        
        command = {"payload": {"action": "help"}}
        result = agent.handle_command(command)
        
        assert result is True


class TestMessageQueue:
    """Tests for message queue functionality."""

    def test_receive_message_adds_to_queue(self, concrete_agent_setup):
        """Test that receive_message adds message to queue."""
        agent, _, _ = concrete_agent_setup
        
        message = {"type": "test", "payload": {}}
        agent.receive_message(message)
        
        assert len(agent.local_message_queue) == 1

    def test_receive_multiple_messages(self, concrete_agent_setup):
        """Test receiving multiple messages."""
        agent, _, _ = concrete_agent_setup
        
        for i in range(5):
            agent.receive_message({"seq": i})
        
        assert len(agent.local_message_queue) == 5

    def test_get_messages_returns_all(self, concrete_agent_setup):
        """Test that get_messages returns all messages and clears queue."""
        agent, _, workspace = concrete_agent_setup
        
        agent.receive_message({"seq": 1})
        agent.receive_message({"seq": 2})
        
        messages = agent.get_messages()
        
        assert len(messages) == 2
        assert len(agent.local_message_queue) == 0
        workspace.log_event.assert_called()

    def test_get_messages_empty_queue(self, concrete_agent_setup):
        """Test get_messages on empty queue."""
        agent, _, workspace = concrete_agent_setup
        
        messages = agent.get_messages()
        
        assert messages == []
        # Should not log when no messages consumed
        assert all(call[0][0] != "MESSAGES_CONSUMED" for call in workspace.log_event.call_args_list)


class TestCommandQueue:
    """Tests for command queue functionality."""

    def test_receive_command_adds_to_queue(self, concrete_agent_setup):
        """Test that receive_command adds command to queue."""
        agent, _, _ = concrete_agent_setup
        
        command = {"payload": {"action": "test"}}
        agent.receive_command(command)
        
        assert len(agent.local_command_queue) == 1

    def test_receive_command_sets_event(self, concrete_agent_setup):
        """Test that receive_command sets the command event."""
        agent, _, _ = concrete_agent_setup
        
        command = {"payload": {"action": "test"}}
        agent.receive_command(command)
        
        assert agent.command_event.is_set()

    def test_multiple_commands_queued(self, concrete_agent_setup):
        """Test multiple commands are queued in order."""
        agent, _, _ = concrete_agent_setup
        
        for i in range(3):
            agent.receive_command({"payload": {"action": f"cmd{i}"}})
        
        assert len(agent.local_command_queue) == 3
        # Check FIFO order
        first = agent.local_command_queue.popleft()
        assert first["payload"]["action"] == "cmd0"


class TestPauseResume:
    """Tests for pause and resume functionality."""

    def test_pause_already_paused(self, concrete_agent_setup):
        """Test pausing an already paused agent shows message."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.PAUSED
        
        agent.pause()
        
        mc.postToChat.assert_called()
        assert "already paused" in mc.postToChat.call_args[0][0].lower()

    def test_resume_not_paused(self, concrete_agent_setup):
        """Test resuming when not paused shows message."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.RUNNING
        
        agent.resume()
        
        mc.postToChat.assert_called()
        assert "not paused" in mc.postToChat.call_args[0][0].lower()

    def test_pause_sets_interrupt_event(self, concrete_agent_setup):
        """Test that pause sets the interrupt event."""
        agent, _, _ = concrete_agent_setup
        agent.state = AgentState.RUNNING
        
        agent.pause()
        
        assert agent.interrupt_event.is_set()

    def test_resume_sets_interrupt_event(self, concrete_agent_setup):
        """Test that resume sets the interrupt event."""
        agent, _, _ = concrete_agent_setup
        agent.state = AgentState.PAUSED
        
        agent.resume()
        
        assert agent.interrupt_event.is_set()


class TestStartStop:
    """Tests for start and stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self, concrete_agent_setup):
        """Test that start creates command and PDA tasks."""
        agent, mc, _ = concrete_agent_setup
        
        with patch('asyncio.create_task') as mock_create_task:
            await agent.start(test_param="value")
            
            assert mock_create_task.call_count == 2
            assert agent.args == {"test_param": "value"}
            
            # Close coroutines
            for call in mock_create_task.call_args_list:
                coro = call.args[0]
                coro.close()

    @pytest.mark.asyncio
    async def test_start_when_stopped(self, concrete_agent_setup):
        """Test that start does not restart a stopped agent."""
        agent, mc, _ = concrete_agent_setup
        agent.state = AgentState.STOPPED
        
        await agent.start()
        
        # Should not create tasks
        assert agent.pda_task is None

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, concrete_agent_setup):
        """Test that start does not double-start an agent."""
        agent, mc, _ = concrete_agent_setup
        
        # Create a mock task that is not done
        mock_task = MagicMock()
        mock_task.done.return_value = False
        agent.pda_task = mock_task
        
        await agent.start()
        
        # Should log warning and not restart
        assert agent.pda_task is mock_task

    def test_stop_sets_flags(self, concrete_agent_setup):
        """Test that stop sets all necessary flags."""
        agent, mc, _ = concrete_agent_setup
        
        agent.stop()
        
        assert agent.should_stop is True
        assert agent.state == AgentState.STOPPED
        assert agent.interrupt_event.is_set()


class TestThreadSafety:
    """Tests for thread-safety of agent operations."""

    def test_concurrent_command_receive(self, concrete_agent_setup):
        """Test thread-safe command receiving."""
        agent, _, _ = concrete_agent_setup
        
        def receive_commands(thread_id):
            for i in range(100):
                agent.receive_command({"thread": thread_id, "seq": i})
        
        threads = [threading.Thread(target=receive_commands, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(agent.local_command_queue) == 500

    def test_concurrent_message_receive(self, concrete_agent_setup):
        """Test thread-safe message receiving."""
        agent, _, _ = concrete_agent_setup
        
        def receive_messages(thread_id):
            for i in range(100):
                agent.receive_message({"thread": thread_id, "seq": i})
        
        threads = [threading.Thread(target=receive_messages, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(agent.local_message_queue) == 500


class TestAgentCycleAsync:
    """Async tests for agent PDA cycle behavior."""

    @pytest.mark.asyncio
    async def test_process_commands_loop_handles_command(self, concrete_agent_setup):
        """Test that command loop processes commands."""
        agent, _, workspace = concrete_agent_setup
        
        # Send command
        agent.receive_command({"payload": {"action": "status"}})
        
        # Run command processing for a short time
        async def run_with_timeout():
            try:
                await asyncio.wait_for(agent.process_commands_loop(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        await run_with_timeout()
        
        # Command should have been processed
        assert len(agent.local_command_queue) == 0

    @pytest.mark.asyncio
    async def test_handle_command_updates_args(self, concrete_agent_setup):
        """Test that start command updates agent args."""
        agent, _, _ = concrete_agent_setup
        
        command = {"payload": {"action": "start", "parameters": {"x": 100, "z": 200}}}
        agent.handle_command(command)
        
        assert agent.args["x"] == 100
        assert agent.args["z"] == 200
