"""
Additional unit tests for Workflow module.

This module provides comprehensive coverage for Workflow functionality including:
- Message processing edge cases
- Stage execution
- Wait conditions and timeouts
- Configuration handling
- Singleton pattern
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from workflow import (
    WorkflowConfig,
    WorkflowState,
    Workflow,
    handle_map_message,
    handle_requirements_message,
    handle_inventory_message,
    handle_build_message,
    process_message,
    build_command,
    build_exploration_params,
    build_mining_params,
    MESSAGE_HANDLERS,
)


class TestWorkflowConfigExtended:
    """Extended tests for WorkflowConfig."""

    def test_config_none_values(self):
        """Test config with explicit None values."""
        params = {"x": None, "z": None}
        config = WorkflowConfig(params)
        
        assert config.x is None
        assert config.z is None

    def test_config_all_miner_params(self):
        """Test config with all miner parameters."""
        params = {
            "miner.strategy": "vein",
            "miner.x": 100,
            "miner.y": 50,
            "miner.z": 200
        }
        config = WorkflowConfig(params)
        
        assert config.miner_strategy == "vein"
        assert config.miner_x == 100
        assert config.miner_y == 50
        assert config.miner_z == 200

    def test_config_string_values(self):
        """Test config preserves string values correctly."""
        params = {"template": "ModernHouse"}
        config = WorkflowConfig(params)
        
        assert config.template == "ModernHouse"


class TestWorkflowStateExtended:
    """Extended tests for WorkflowState."""

    def test_state_chained_updates(self):
        """Test chaining multiple state updates."""
        state = WorkflowState()
        
        state2 = state.update(exploration_complete=True)
        state3 = state2.update(materials_requested=True)
        state4 = state3.update(mining_complete=True, current_stage=3)
        
        # Original state unchanged
        assert state.exploration_complete is False
        assert state.current_stage == 0
        
        # Final state has all updates
        assert state4.exploration_complete is True
        assert state4.materials_requested is True
        assert state4.mining_complete is True
        assert state4.current_stage == 3

    def test_state_full_initialization(self):
        """Test WorkflowState with all parameters."""
        state = WorkflowState(
            exploration_complete=True,
            materials_requested=True,
            mining_complete=True,
            build_complete=True,
            current_stage=4
        )
        
        assert state.exploration_complete is True
        assert state.materials_requested is True
        assert state.mining_complete is True
        assert state.build_complete is True
        assert state.current_stage == 4


class TestMessageHandlersExtended:
    """Extended tests for message handler functions."""

    def test_handle_build_message_in_progress(self):
        """Test build message with IN_PROGRESS status."""
        state = WorkflowState()
        message = {"type": "build.v1", "status": "IN_PROGRESS"}
        
        new_state = handle_build_message(state, message)
        
        assert new_state.build_complete is False

    def test_handle_build_message_failed(self):
        """Test build message with FAILED status."""
        state = WorkflowState()
        message = {"type": "build.v1", "status": "FAILED"}
        
        new_state = handle_build_message(state, message)
        
        assert new_state.build_complete is False

    def test_handle_inventory_message_partial(self):
        """Test inventory message with partial completion."""
        state = WorkflowState()
        message = {
            "type": "inventory.v1",
            "payload": {
                "complete": False,
                "materials": [{"material": "STONE", "collected": 5}]
            }
        }
        
        new_state = handle_inventory_message(state, message)
        
        assert new_state.mining_complete is False

    def test_handle_map_message_preserves_other_state(self):
        """Test that map handler preserves other state fields."""
        state = WorkflowState(materials_requested=True, current_stage=1)
        message = {"type": "map.v1", "payload": {}}
        
        new_state = handle_map_message(state, message)
        
        assert new_state.exploration_complete is True
        assert new_state.materials_requested is True
        assert new_state.current_stage == 1


class TestProcessMessage:
    """Tests for process_message function."""

    def test_process_unknown_message_type(self):
        """Test processing an unknown message type."""
        state = WorkflowState()
        message = {"type": "unknown.v1", "payload": {}}
        
        new_state = process_message(state, message)
        
        # State should be unchanged
        assert new_state.exploration_complete is False
        assert new_state.materials_requested is False

    def test_process_message_empty_type(self):
        """Test processing a message with no type."""
        state = WorkflowState()
        message = {"payload": {}}
        
        new_state = process_message(state, message)
        
        # Should not crash and state should be unchanged
        assert new_state.exploration_complete is False

    def test_message_handlers_mapping(self):
        """Test that all expected handlers are in MESSAGE_HANDLERS."""
        expected_types = ["map.v1", "materials.requirements.v1", "inventory.v1", "build.v1"]
        
        for msg_type in expected_types:
            assert msg_type in MESSAGE_HANDLERS


class TestBuildCommand:
    """Tests for build_command function."""

    @pytest.mark.asyncio
    async def test_build_command_structure(self):
        """Test that build_command creates proper structure."""
        command = build_command("ExplorerBot", "start", {"x": 10}, stage=1)
        
        assert command["target"] == "ExplorerBot"
        assert command["payload"]["action"] == "start"
        assert command["payload"]["parameters"]["x"] == 10
        assert command["context"]["workflow_stage"] == 1

    @pytest.mark.asyncio
    async def test_build_command_empty_params(self):
        """Test build_command with empty parameters."""
        command = build_command("BuilderBot", "build", {}, stage=3)
        
        assert command["payload"]["parameters"] == {}


class TestBuildExplorationParams:
    """Tests for build_exploration_params function."""

    def test_build_exploration_params_all(self):
        """Test building params with all values."""
        config = WorkflowConfig({"x": 100, "z": 200, "range": 64})
        
        params = build_exploration_params(config)
        
        assert params["x"] == 100
        assert params["z"] == 200
        assert params["range"] == 64

    def test_build_exploration_params_partial(self):
        """Test building params with partial values."""
        config = WorkflowConfig({"range": 48})
        
        params = build_exploration_params(config)
        
        assert "x" not in params
        assert "z" not in params
        assert params["range"] == 48

    def test_build_exploration_params_defaults(self):
        """Test building params with default range."""
        config = WorkflowConfig({})
        
        params = build_exploration_params(config)
        
        assert params["range"] == 32


class TestBuildMiningParams:
    """Tests for build_mining_params function."""

    def test_build_mining_params_all(self):
        """Test building mining params with all values."""
        config = WorkflowConfig({
            "miner.strategy": "grid",
            "miner.x": 50,
            "miner.y": 30,
            "miner.z": 100
        })
        
        params = build_mining_params(config)
        
        assert params["strategy"] == "grid"
        assert params["x"] == 50
        assert params["y"] == 30
        assert params["z"] == 100

    def test_build_mining_params_strategy_only(self):
        """Test building mining params with strategy only."""
        config = WorkflowConfig({"miner.strategy": "vein"})
        
        params = build_mining_params(config)
        
        assert params["strategy"] == "vein"
        assert "x" not in params
        assert "y" not in params
        assert "z" not in params

    def test_build_mining_params_defaults(self):
        """Test building mining params with defaults."""
        config = WorkflowConfig({})
        
        params = build_mining_params(config)
        
        assert params["strategy"] == "vertical"


class TestWorkflowSingleton:
    """Tests for Workflow singleton pattern."""

    def test_singleton_instance(self):
        """Test that Workflow is a singleton."""
        mc1 = MagicMock()
        workspace1 = MagicMock()
        agents1 = []
        
        Workflow._instance = None  # Reset singleton
        
        wf1 = Workflow(mc1, workspace1, agents1)
        wf2 = Workflow(mc1, workspace1, agents1)
        
        assert wf1 is wf2

    def test_get_instance_returns_singleton(self):
        """Test get_instance returns the singleton."""
        Workflow._instance = None
        
        mc = MagicMock()
        workspace = MagicMock()
        
        wf = Workflow(mc, workspace, [])
        
        assert Workflow.get_instance() is wf

    def test_get_instance_returns_none_when_not_created(self):
        """Test get_instance returns None when no instance exists."""
        Workflow._instance = None
        
        assert Workflow.get_instance() is None


@pytest.fixture
def workflow_setup(tmp_path):
    """Create a workflow with mocked dependencies."""
    Workflow._instance = None
    
    mc = MagicMock()
    workspace = MagicMock()
    workspace.log_file = str(tmp_path / "workflow.log")
    
    class MockAgent:
        def __init__(self, name):
            self.__class__.__name__ = name
    
    agents = [MockAgent("ExplorerBot"), MockAgent("MinerBot"), MockAgent("BuilderBot")]
    
    workflow = Workflow(mc, workspace, agents)
    return workflow, mc, workspace


class TestWorkflowMethods:
    """Tests for Workflow instance methods."""

    def test_receive_message_relevant(self, workflow_setup):
        """Test receiving a relevant message."""
        workflow, _, _ = workflow_setup
        
        message = {"type": "map.v1", "payload": {}}
        workflow.receive_message(message)
        
        assert not workflow.message_queue.empty()

    def test_receive_message_irrelevant(self, workflow_setup):
        """Test receiving an irrelevant message."""
        workflow, _, _ = workflow_setup
        
        message = {"type": "unknown.v1", "payload": {}}
        workflow.receive_message(message)
        
        assert workflow.message_queue.empty()

    def test_stop_sets_flag(self, workflow_setup):
        """Test that stop sets should_stop flag."""
        workflow, mc, _ = workflow_setup
        
        workflow.stop()
        
        assert workflow.should_stop is True
        mc.postToChat.assert_called()

    def test_help_displays_commands(self, workflow_setup):
        """Test that help displays help text."""
        workflow, mc, _ = workflow_setup
        
        workflow.help()
        
        assert mc.postToChat.call_count >= 1

    @pytest.mark.asyncio
    async def test_run_already_running(self, workflow_setup):
        """Test that run does not start when already running."""
        workflow, mc, _ = workflow_setup
        workflow.is_running = True
        
        await workflow.run({})
        
        mc.postToChat.assert_called_with("Workflow is already running")

    @pytest.mark.asyncio
    async def test_process_messages_updates_state(self, workflow_setup):
        """Test that _process_messages updates state correctly."""
        workflow, _, _ = workflow_setup
        
        workflow.message_queue.put_nowait({"type": "map.v1", "payload": {}})
        
        await workflow._process_messages()
        
        assert workflow.state.exploration_complete is True

    @pytest.mark.asyncio
    async def test_process_messages_empty_queue(self, workflow_setup):
        """Test _process_messages with empty queue."""
        workflow, _, _ = workflow_setup
        
        await workflow._process_messages()
        
        # Should not crash
        assert workflow.message_queue.empty()

    def test_reset_clears_state(self, workflow_setup):
        """Test that _reset clears workflow state."""
        workflow, _, _ = workflow_setup
        
        workflow.state = WorkflowState(exploration_complete=True, current_stage=2)
        workflow.should_stop = True
        workflow.message_queue.put_nowait({"type": "test"})
        
        workflow._reset()
        
        assert workflow.state.exploration_complete is False
        assert workflow.state.current_stage == 0
        assert workflow.is_running is True
        assert workflow.should_stop is False
        assert workflow.message_queue.empty()

    def test_config_summary(self, workflow_setup):
        """Test _config_summary returns correct dict."""
        workflow, _, _ = workflow_setup
        workflow.config = WorkflowConfig({
            "x": 10, "z": 20, "range": 32,
            "template": "Tower",
            "miner.strategy": "vertical"
        })
        
        summary = workflow._config_summary()
        
        assert summary["x"] == 10
        assert summary["z"] == 20
        assert summary["range"] == 32
        assert summary["template"] == "Tower"

    @pytest.mark.asyncio
    async def test_send_command(self, workflow_setup):
        """Test _send_command posts command to workspace."""
        workflow, _, workspace = workflow_setup
        
        workflow._send_command("ExplorerBot", "start", {"x": 10})
        
        workspace.post_command.assert_called_once()

    def test_log_event(self, workflow_setup):
        """Test _log logs event with stage."""
        workflow, _, workspace = workflow_setup
        workflow.state = WorkflowState(current_stage=2)
        
        workflow._log("TEST_EVENT", {"data": "value"})
        
        workspace.log_event.assert_called()
        call_args = workspace.log_event.call_args
        assert "stage" in call_args[0][2]


class TestWorkflowStages:
    """Tests for workflow stage execution."""

    @pytest.mark.asyncio
    async def test_stage_exploration(self, workflow_setup):
        """Test exploration stage sends command."""
        workflow, _, workspace = workflow_setup
        workflow.config = WorkflowConfig({"x": 100, "z": 200, "range": 64})
        
        await workflow._stage_exploration()
        
        workspace.post_command.assert_called()

    @pytest.mark.asyncio
    async def test_stage_planning(self, workflow_setup):
        """Test planning stage sends command."""
        workflow, _, workspace = workflow_setup
        workflow.config = WorkflowConfig({"template": "ModernHouse"})
        
        await workflow._stage_planning()
        
        workspace.post_command.assert_called()

    @pytest.mark.asyncio
    async def test_stage_mining(self, workflow_setup):
        """Test mining stage sends commands."""
        workflow, _, workspace = workflow_setup
        workflow.config = WorkflowConfig({"miner.strategy": "grid"})
        
        await workflow._stage_mining()
        
        # Should send both set and start commands
        assert workspace.post_command.call_count >= 1

    @pytest.mark.asyncio
    async def test_stage_building(self, workflow_setup):
        """Test building stage sends command."""
        workflow, _, workspace = workflow_setup
        workflow.config = WorkflowConfig({})
        
        await workflow._stage_building()
        
        workspace.post_command.assert_called()


class TestWaitFor:
    """Tests for _wait_for method."""

    @pytest.mark.asyncio
    async def test_wait_for_condition_met(self, workflow_setup):
        """Test wait_for when condition is immediately met."""
        workflow, _, _ = workflow_setup
        workflow.config = WorkflowConfig({})
        
        # Condition is immediately true
        await workflow._wait_for(lambda: True, 1.0, "Test")
        
        # Should return immediately without timeout

    @pytest.mark.asyncio
    async def test_wait_for_should_stop(self, workflow_setup):
        """Test wait_for raises CancelledError when stopped."""
        workflow, _, _ = workflow_setup
        workflow.config = WorkflowConfig({})
        workflow.should_stop = True
        
        with pytest.raises(asyncio.CancelledError):
            await workflow._wait_for(lambda: False, 1.0, "Test")

    @pytest.mark.asyncio
    async def test_wait_for_timeout(self, workflow_setup):
        """Test wait_for times out correctly."""
        workflow, mc, _ = workflow_setup
        workflow.config = WorkflowConfig({})
        
        await workflow._wait_for(lambda: False, 0.1, "TestStage")
        
        # Should log timeout
        mc.postToChat.assert_called()
