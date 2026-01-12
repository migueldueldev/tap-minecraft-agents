import pytest
import json
import os
from unittest.mock import MagicMock, mock_open, patch
from shared_workspace import SharedWorkspace


class AgentA:
    """Mock agent for testing purposes"""
    def __init__(self):
        self.args = {"param": 1}
        self.receive_command = MagicMock()
        self.receive_message = MagicMock()
    
    def get_state(self):
        mock_state = MagicMock()
        mock_state.value = "RUNNING"
        return mock_state


class AgentB:
    """Second mock agent for testing message routing"""
    def __init__(self):
        self.receive_command = MagicMock()
        self.receive_message = MagicMock()


@pytest.fixture
def workspace(tmp_path):
    """Create a shared workspace with a temporary log file"""
    ws = SharedWorkspace()
    log_file = tmp_path / "test_execution.log"
    ws.log_file = str(log_file)
    return ws


class TestObserverManagement:
    """Tests for observer registration and removal"""
    
    def test_register_observer(self, workspace):
        """Test registering an observer"""
        agent = AgentA()
        workspace.register_observer(agent)
        assert agent in workspace.observers
        assert len(workspace.observers) == 1
    
    def test_register_duplicate_observer(self, workspace):
        """Test that duplicate registrations are ignored"""
        agent = AgentA()
        workspace.register_observer(agent)
        workspace.register_observer(agent)
        assert len(workspace.observers) == 1
    
    def test_remove_observer(self, workspace):
        """Test removing an observer"""
        agent = AgentA()
        workspace.register_observer(agent)
        workspace.remove_observer(agent)
        assert agent not in workspace.observers
        assert len(workspace.observers) == 0
    
    def test_remove_nonexistent_observer(self, workspace):
        """Test that removing a non-registered observer does not raise an error"""
        agent = AgentA()
        # Should not raise an error
        workspace.remove_observer(agent)
        assert len(workspace.observers) == 0


class TestMessageRouting:
    """Tests for command and message routing"""
    
    def test_post_command_to_specific_agent(self, workspace):
        """Test that commands are routed to the correct agent"""
        agent_a = AgentA()
        agent_b = AgentB()
        workspace.register_observer(agent_a)
        workspace.register_observer(agent_b)
        
        command = {"action": "move"}
        workspace.post_command("AgentA", command)
        
        agent_a.receive_command.assert_called_once_with(command)
        agent_b.receive_command.assert_not_called()
    
    def test_post_message_to_target(self, workspace):
        """Test that messages are routed to the target agent"""
        agent_a = AgentA()
        agent_b = AgentB()
        workspace.register_observer(agent_a)
        workspace.register_observer(agent_b)
        
        message = {
            "type": "test.v1",
            "source": "AgentA",
            "target": "AgentB",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {"content": "hello"},
            "status": "SUCCESS"
        }
        workspace.post_message(message)
        
        agent_b.receive_message.assert_called_once_with(message)
        agent_a.receive_message.assert_not_called()
    
    def test_post_command_to_unknown_agent(self, workspace):
        """Test posting command to an agent that does not exist"""
        agent_a = AgentA()
        workspace.register_observer(agent_a)
        
        command = {"action": "move"}
        # Should just not deliver to anyone
        workspace.post_command("UnknownAgent", command)
        agent_a.receive_command.assert_not_called()


class TestLogging:
    """Tests for event logging functionality"""
    
    def test_log_event_writes_to_file(self, workspace):
        """Test that log_event writes properly formatted JSON"""
        with patch("builtins.open", mock_open()) as mocked_file:
            workspace.log_event("TEST_EVENT", "AgentA", {"payload": 123})
            mocked_file.assert_called_once_with(workspace.log_file, 'a', encoding='utf-8')
            
            handle = mocked_file()
            args, _ = handle.write.call_args
            log_data = json.loads(args[0])
            assert log_data["event"] == "TEST_EVENT"
            assert log_data["agent"] == "AgentA"
            assert log_data["data"] == {"payload": 123}
            assert "timestamp" in log_data
    
    def test_save_final_state(self, workspace):
        """Test saving final system state"""
        agent = AgentA()
        with patch("builtins.open", mock_open()) as mocked_file:
            workspace.save_final_state([agent])
            handle = mocked_file()
            written_content = "".join(call.args[0] for call in handle.write.call_args_list)
            final_state = json.loads(written_content)
            
            assert final_state["event"] == "SYSTEM_SHUTDOWN"
            assert final_state["agents"][0]["name"] == "AgentA"
            assert final_state["agents"][0]["state"] == "RUNNING"
            assert final_state["agents"][0]["args"] == {"param": 1}
            assert "timestamp" in final_state
    
    def test_save_final_state_multiple_agents(self, workspace):
        """Test saving final state with multiple agents"""
        agent_a = AgentA()
        agent_b = AgentB()
        agent_b.args = {"param": 2}
        agent_b.get_state = lambda: MagicMock(value="IDLE")
        
        with patch("builtins.open", mock_open()) as mocked_file:
            workspace.save_final_state([agent_a, agent_b])
            handle = mocked_file()
            written_content = "".join(call.args[0] for call in handle.write.call_args_list)
            final_state = json.loads(written_content)
            
            assert len(final_state["agents"]) == 2
            assert final_state["agents"][0]["name"] == "AgentA"
            assert final_state["agents"][1]["name"] == "AgentB"


def test_register_and_remove_observer(workspace):
    """Register and remove observer"""
    agent = AgentA()
    workspace.register_observer(agent)
    assert agent in workspace.observers
    assert len(workspace.observers) == 1
    
    workspace.register_observer(agent)
    assert len(workspace.observers) == 1
    
    workspace.remove_observer(agent)
    assert agent not in workspace.observers
    assert len(workspace.observers) == 0


def test_post_command(workspace):
    """Post command to specific agent"""
    agent_a = AgentA()
    agent_b = AgentB()
    workspace.register_observer(agent_a)
    workspace.register_observer(agent_b)
    
    command = {"action": "move"}
    workspace.post_command("AgentA", command)
    
    agent_a.receive_command.assert_called_once_with(command)
    agent_b.receive_command.assert_not_called()


def test_post_message(workspace):
    """Post message to target agent"""
    agent_a = AgentA()
    agent_b = AgentB()
    workspace.register_observer(agent_a)
    workspace.register_observer(agent_b)
    
    message = {
        "type": "test.v1",
        "source": "AgentA",
        "target": "AgentB",
        "timestamp": "2026-01-01T00:00:00Z",
        "payload": {"content": "hello"},
        "status": "SUCCESS"
    }
    workspace.post_message(message)
    
    agent_b.receive_message.assert_called_once_with(message)
    agent_a.receive_message.assert_not_called()


def test_log_event(workspace):
    """Log event to file"""
    with patch("builtins.open", mock_open()) as mocked_file:
        workspace.log_event("TEST_EVENT", "AgentA", {"payload": 123})
        mocked_file.assert_called_once_with(workspace.log_file, 'a', encoding='utf-8')
        
        handle = mocked_file()
        args, _ = handle.write.call_args
        log_data = json.loads(args[0])
        assert log_data["event"] == "TEST_EVENT"
        assert log_data["agent"] == "AgentA"
        assert log_data["data"] == {"payload": 123}


def test_save_final_state(workspace):
    """Save final system state"""
    agent = AgentA()
    with patch("builtins.open", mock_open()) as mocked_file:
        workspace.save_final_state([agent])
        handle = mocked_file()
        written_content = "".join(call.args[0] for call in handle.write.call_args_list)
        final_state = json.loads(written_content)
        
        assert final_state["event"] == "SYSTEM_SHUTDOWN"
        assert final_state["agents"][0]["name"] == "AgentA"
        assert final_state["agents"][0]["state"] == "RUNNING"
        assert final_state["agents"][0]["args"] == {"param": 1}