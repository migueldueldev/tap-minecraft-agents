import pytest
import asyncio
from unittest.mock import MagicMock, patch
from base_agent import BaseAgent, AgentState

class MockAgent(BaseAgent):
    async def perceive(self, **kwargs):
        pass
    async def decide(self, **kwargs):
        pass
    async def act(self, **kwargs):
        pass

@pytest.fixture
def agent_setup():
    mc = MagicMock()
    workspace = MagicMock()
    agent = MockAgent(mc, workspace)
    return agent, mc, workspace

def test_initialization(agent_setup):
    agent, mc, workspace = agent_setup
    assert agent.state == AgentState.IDLE
    workspace.register_observer.assert_called_once_with(agent)

def test_receive_command(agent_setup):
    agent, _, _ = agent_setup
    command = {"payload": {"action": "test"}}
    agent.receive_command(command)
    assert len(agent.local_command_queue) == 1
    assert agent.command_event.is_set()

def test_receive_and_get_messages(agent_setup):
    agent, _, workspace = agent_setup
    agent.receive_message("msg1")
    agent.receive_message("msg2")
    
    messages = agent.get_messages()
    assert messages == ["msg1", "msg2"]
    assert len(agent.local_message_queue) == 0
    workspace.log_event.assert_called_with("MESSAGES_CONSUMED", "MockAgent", {"count": 2})

def test_set_state(agent_setup):
    agent, _, workspace = agent_setup
    agent.set_state(AgentState.RUNNING, reason="testing")
    assert agent.state == AgentState.RUNNING
    workspace.log_event.assert_called()
    call_args = workspace.log_event.call_args
    assert call_args[0][0] == "STATE_CHANGE"
    assert call_args[0][2]["new_state"] == "RUNNING"
    assert call_args[0][2]["reason"] == "testing"

def test_handle_command_start(agent_setup):
    agent, _, _ = agent_setup
    command = {"payload": {"action": "start", "parameters": {"key": "val"}}}
    result = agent.handle_command(command)
    assert result is True
    assert agent.args == {"key": "val"}
    assert agent.state == AgentState.RUNNING

def test_handle_command_stop(agent_setup):
    agent, mc, _ = agent_setup
    command = {"payload": {"action": "stop"}}
    agent.handle_command(command)
    assert agent.should_stop is True
    assert agent.state == AgentState.STOPPED
    mc.postToChat.assert_called_with("Agent MockAgent stopped.")

def test_pause_resume(agent_setup):
    agent, _, _ = agent_setup
    agent.pause()
    assert agent.state == AgentState.PAUSED
    agent.resume()
    assert agent.state == AgentState.RUNNING

@pytest.mark.asyncio
async def test_start_method(agent_setup):
    agent, _, _ = agent_setup
    # Mock task creation to avoid actual loop execution
    with patch('asyncio.create_task') as mock_task:
        await agent.start(param1="test")
        assert agent.args == {"param1": "test"}
        assert agent.should_stop is False
        assert mock_task.call_count == 2
        
        # Close the coroutines
        for call in mock_task.call_args_list:
            coro = call.args[0]
            coro.close()


@pytest.mark.asyncio
async def test_stop_method(agent_setup):
    """Test that stop properly sets agent state and flags"""
    agent, mc, _ = agent_setup
    agent.stop()
    assert agent.should_stop is True
    assert agent.state == AgentState.STOPPED
    assert agent.interrupt_event.is_set()
    mc.postToChat.assert_called_with("Agent MockAgent stopped.")


def test_status_method(agent_setup):
    """Test that status posts current state to chat"""
    agent, mc, _ = agent_setup
    agent.set_state(AgentState.RUNNING)
    agent.status()
    mc.postToChat.assert_called_with("Agent MockAgent status: RUNNING")


def test_help_method(agent_setup):
    """Test that help posts help text to chat"""
    agent, mc, _ = agent_setup
    agent.help()
    assert mc.postToChat.call_count >= 1


def test_get_state(agent_setup):
    """Test that state getter returns current state"""
    agent, _, _ = agent_setup
    agent.state = AgentState.WAITING
    assert agent.get_state() == AgentState.WAITING