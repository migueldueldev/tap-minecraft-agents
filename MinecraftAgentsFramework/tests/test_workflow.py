"""
Unit tests for Workflow module.

This module tests the Workflow class and related functions including:
- WorkflowConfig initialization
- WorkflowState management
- Message handlers
- Command building
- Workflow orchestration
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


class TestWorkflowConfig:
    """Tests for WorkflowConfig initialization."""

    def test_default_values(self):
        """Test that default values are correctly set."""
        config = WorkflowConfig({})
        assert config.x is None
        assert config.z is None
        assert config.range == 32
        assert config.template == "Tower"
        assert config.miner_strategy == "vertical"
        assert config.miner_x is None
        assert config.miner_y is None
        assert config.miner_z is None

    def test_custom_values(self):
        """Test that custom values override defaults."""
        params = {
            "x": 100,
            "z": 200,
            "range": 64,
            "template": "ModernHouse",
            "miner.strategy": "grid",
            "miner.x": 10,
            "miner.y": 20,
            "miner.z": 30,
        }
        config = WorkflowConfig(params)
        assert config.x == 100
        assert config.z == 200
        assert config.range == 64
        assert config.template == "ModernHouse"
        assert config.miner_strategy == "grid"
        assert config.miner_x == 10
        assert config.miner_y == 20
        assert config.miner_z == 30

    def test_partial_custom_values(self):
        """Test mixing custom and default values."""
        params = {"x": 50, "template": "SmallIsland"}
        config = WorkflowConfig(params)
        assert config.x == 50
        assert config.z is None
        assert config.range == 32
        assert config.template == "SmallIsland"
        assert config.miner_strategy == "vertical"


class TestWorkflowState:
    """Tests for WorkflowState management."""

    def test_default_initialization(self):
        """Test default state initialization."""
        state = WorkflowState()
        assert state.exploration_complete is False
        assert state.materials_requested is False
        assert state.mining_complete is False
        assert state.build_complete is False
        assert state.current_stage == 0

    def test_custom_initialization(self):
        """Test custom state initialization."""
        state = WorkflowState(
            exploration_complete=True,
            materials_requested=True,
            mining_complete=False,
            build_complete=False,
            current_stage=2,
        )
        assert state.exploration_complete is True
        assert state.materials_requested is True
        assert state.mining_complete is False
        assert state.build_complete is False
        assert state.current_stage == 2

    def test_update_single_field(self):
        """Test updating a single field returns new state."""
        state = WorkflowState()
        new_state = state.update(exploration_complete=True)
        
        # Original unchanged
        assert state.exploration_complete is False
        # New state updated
        assert new_state.exploration_complete is True
        assert new_state.materials_requested is False

    def test_update_multiple_fields(self):
        """Test updating multiple fields at once."""
        state = WorkflowState()
        new_state = state.update(
            exploration_complete=True,
            materials_requested=True,
            current_stage=1,
        )
        assert new_state.exploration_complete is True
        assert new_state.materials_requested is True
        assert new_state.current_stage == 1
        assert new_state.mining_complete is False

    def test_update_preserves_unmodified_fields(self):
        """Test that update preserves fields not being modified."""
        state = WorkflowState(exploration_complete=True, current_stage=1)
        new_state = state.update(materials_requested=True)
        
        assert new_state.exploration_complete is True
        assert new_state.current_stage == 1
        assert new_state.materials_requested is True


class TestMessageHandlers:
    """Tests for individual message handler functions."""

    def test_handle_map_message(self):
        """Test map message handler sets exploration_complete."""
        state = WorkflowState()
        message = {"type": "map.v1", "payload": {}}
        
        new_state = handle_map_message(state, message)
        
        assert new_state.exploration_complete is True
        assert state.exploration_complete is False  # Original unchanged

    def test_handle_requirements_message(self):
        """Test requirements message handler sets materials_requested."""
        state = WorkflowState()
        message = {"type": "materials.requirements.v1", "payload": {}}
        
        new_state = handle_requirements_message(state, message)
        
        assert new_state.materials_requested is True

    def test_handle_inventory_message_complete(self):
        """Test inventory message with complete=True sets mining_complete."""
        state = WorkflowState()
        message = {"type": "inventory.v1", "payload": {"complete": True}}
        
        new_state = handle_inventory_message(state, message)
        
        assert new_state.mining_complete is True

    def test_handle_inventory_message_incomplete(self):
        """Test inventory message with complete=False does not change state."""
        state = WorkflowState()
        message = {"type": "inventory.v1", "payload": {"complete": False}}
        
        new_state = handle_inventory_message(state, message)
        
        assert new_state.mining_complete is False

    def test_handle_inventory_message_no_complete_field(self):
        """Test inventory message without complete field does not change state."""
        state = WorkflowState()
        message = {"type": "inventory.v1", "payload": {}}
        
        new_state = handle_inventory_message(state, message)
        
        assert new_state.mining_complete is False

    def test_handle_build_message_completed(self):
        """Test build message with COMPLETED status sets build_complete."""
        state = WorkflowState()
        message = {"type": "build.v1", "status": "COMPLETED"}
        
        new_state = handle_build_message(state, message)
        
        assert new_state.build_complete is True

    def test_handle_build_message_in_progress(self):
        """Test build message with non-COMPLETED status does not change state."""
        state = WorkflowState()
        message = {"type": "build.v1", "status": "IN_PROGRESS"}
        
        new_state = handle_build_message(state, message)
        
        assert new_state.build_complete is False


class TestProcessMessage:
    """Tests for the process_message function."""

    def test_process_map_message(self):
        """Test processing map.v1 message."""
        state = WorkflowState()
        message = {"type": "map.v1", "payload": {}}
        
        new_state = process_message(state, message)
        
        assert new_state.exploration_complete is True

    def test_process_requirements_message(self):
        """Test processing materials.requirements.v1 message."""
        state = WorkflowState()
        message = {"type": "materials.requirements.v1", "payload": {}}
        
        new_state = process_message(state, message)
        
        assert new_state.materials_requested is True

    def test_process_inventory_message(self):
        """Test processing inventory.v1 message."""
        state = WorkflowState()
        message = {"type": "inventory.v1", "payload": {"complete": True}}
        
        new_state = process_message(state, message)
        
        assert new_state.mining_complete is True

    def test_process_build_message(self):
        """Test processing build.v1 message."""
        state = WorkflowState()
        message = {"type": "build.v1", "status": "COMPLETED"}
        
        new_state = process_message(state, message)
        
        assert new_state.build_complete is True

    def test_process_unknown_message_type(self):
        """Test that unknown message types do not change state."""
        state = WorkflowState()
        message = {"type": "unknown.v1", "payload": {}}
        
        new_state = process_message(state, message)
        
        # State should be unchanged
        assert new_state.exploration_complete is False
        assert new_state.materials_requested is False
        assert new_state.mining_complete is False
        assert new_state.build_complete is False

    def test_process_message_missing_type(self):
        """Test message without type field is handled gracefully."""
        state = WorkflowState()
        message = {"payload": {}}
        
        new_state = process_message(state, message)
        
        # State should be unchanged
        assert new_state.exploration_complete is False


class TestBuildCommand:
    """Tests for the build_command function."""

    @pytest.mark.asyncio
    async def test_build_command_structure(self):
        """Test that build_command creates proper command structure."""
        command = build_command("ExplorerBot", "start", {"range": 32}, 0)
        
        assert command["type"] == "command.control.v1"
        assert command["source"] == "Workflow"
        assert command["target"] == "ExplorerBot"
        assert command["status"] == "SUCCESS"
        assert command["payload"]["action"] == "start"
        assert command["payload"]["parameters"] == {"range": 32}
        assert command["context"]["workflow_stage"] == 0

    @pytest.mark.asyncio
    async def test_build_command_timestamp_format(self):
        """Test that timestamp is in ISO format with Z suffix."""
        command = build_command("MinerBot", "fulfill", {}, 2)
        
        timestamp = command["timestamp"]
        assert timestamp.endswith("Z")
        # Should be parseable as ISO format (remove trailing Z)
        datetime.fromisoformat(timestamp[:-1])

    @pytest.mark.asyncio
    async def test_build_command_different_stages(self):
        """Test command with different workflow stages."""
        command_stage_0 = build_command("BuilderBot", "plan", {}, 0)
        command_stage_3 = build_command("BuilderBot", "build", {}, 3)
        
        assert command_stage_0["context"]["workflow_stage"] == 0
        assert command_stage_3["context"]["workflow_stage"] == 3


class TestBuildExplorationParams:
    """Tests for build_exploration_params function."""

    def test_with_all_params(self):
        """Test building params with all values set."""
        config = WorkflowConfig({"x": 100, "z": 200, "range": 64})
        params = build_exploration_params(config)
        
        assert params["x"] == 100
        assert params["z"] == 200
        assert params["range"] == 64

    def test_with_only_range(self):
        """Test building params with only range set."""
        config = WorkflowConfig({})
        params = build_exploration_params(config)
        
        assert params["range"] == 32
        assert "x" not in params
        assert "z" not in params

    def test_with_partial_coordinates(self):
        """Test with only x coordinate set."""
        config = WorkflowConfig({"x": 50})
        params = build_exploration_params(config)
        
        assert params["x"] == 50
        assert "z" not in params
        assert params["range"] == 32


class TestBuildMiningParams:
    """Tests for build_mining_params function."""

    def test_with_all_params(self):
        """Test building mining params with all values."""
        config = WorkflowConfig({
            "miner.strategy": "grid",
            "miner.x": 10,
            "miner.y": 20,
            "miner.z": 30,
        })
        params = build_mining_params(config)
        
        assert params["strategy"] == "grid"
        assert params["x"] == 10
        assert params["y"] == 20
        assert params["z"] == 30

    def test_with_only_strategy(self):
        """Test building params with only strategy."""
        config = WorkflowConfig({})
        params = build_mining_params(config)
        
        assert params["strategy"] == "vertical"
        assert "x" not in params
        assert "y" not in params
        assert "z" not in params

    def test_with_partial_coordinates(self):
        """Test with some coordinates set."""
        config = WorkflowConfig({"miner.x": 5, "miner.y": 10})
        params = build_mining_params(config)
        
        assert params["strategy"] == "vertical"
        assert params["x"] == 5
        assert params["y"] == 10
        assert "z" not in params


class TestWorkflowClass:
    """Tests for the Workflow class."""

    @pytest.fixture
    def mock_mc(self):
        """Create mock Minecraft connection."""
        mc = MagicMock()
        mc.postToChat = MagicMock()
        return mc

    @pytest.fixture
    def mock_workspace(self):
        """Create mock SharedWorkspace."""
        workspace = MagicMock()
        workspace.register_workflow_observer = MagicMock()
        workspace.post_command = MagicMock()
        workspace.log_event = MagicMock()
        return workspace

    @pytest.fixture
    def mock_agents(self):
        """Create mock agent instances."""
        class MockExplorer:
            pass
        class MockMiner:
            pass
        class MockBuilder:
            pass
        
        explorer = MockExplorer()
        explorer.__class__.__name__ = "ExplorerBot"
        miner = MockMiner()
        miner.__class__.__name__ = "MinerBot"
        builder = MockBuilder()
        builder.__class__.__name__ = "BuilderBot"
        
        return [explorer, miner, builder]

    @pytest.fixture
    def workflow(self, mock_mc, mock_workspace, mock_agents):
        """Create Workflow instance with mocks."""
        return Workflow(mock_mc, mock_workspace, mock_agents)

    def test_initialization(self, workflow, mock_workspace):
        """Test Workflow initialization."""
        assert workflow.is_running is False
        assert workflow.should_stop is False
        assert workflow.config is None
        assert isinstance(workflow.state, WorkflowState)
        mock_workspace.register_workflow_observer.assert_called_once_with(workflow)

    def test_agents_dictionary(self, workflow):
        """Test that agents are stored in dictionary by class name."""
        assert "ExplorerBot" in workflow.agents
        assert "MinerBot" in workflow.agents
        assert "BuilderBot" in workflow.agents

    def test_receive_message_observable(self, workflow):
        """Test receiving observable message types."""
        message = {"type": "map.v1", "payload": {}}
        workflow.receive_message(message)
        
        assert workflow.message_queue.qsize() == 1

    def test_receive_message_non_observable(self, workflow):
        """Test that non-observable messages are ignored."""
        message = {"type": "unknown.v1", "payload": {}}
        workflow.receive_message(message)
        
        assert workflow.message_queue.empty()

    def test_stop(self, workflow, mock_mc):
        """Test stop method sets flag and posts chat message."""
        workflow.stop()
        
        assert workflow.should_stop is True
        mock_mc.postToChat.assert_called_with("Workflow stopping...")

    def test_help(self, workflow, mock_mc):
        """Test help method posts help messages."""
        workflow.help()
        
        assert mock_mc.postToChat.call_count == 5

    def test_reset(self, workflow):
        """Test _reset method resets state."""
        workflow.state = WorkflowState(exploration_complete=True, current_stage=2)
        workflow.should_stop = True
        workflow.message_queue.put_nowait({"type": "test"})
        
        workflow._reset()
        
        assert workflow.is_running is True
        assert workflow.should_stop is False
        assert workflow.state.exploration_complete is False
        assert workflow.state.current_stage == 0
        assert workflow.message_queue.empty()

    @pytest.mark.asyncio
    async def test_send_command(self, workflow, mock_workspace):
        """Test _send_command sends to workspace."""
        workflow.state = WorkflowState(current_stage=1)
        workflow._send_command("ExplorerBot", "start", {"range": 32})
        
        mock_workspace.post_command.assert_called_once()
        args = mock_workspace.post_command.call_args[0]
        assert args[0] == "ExplorerBot"
        assert args[1]["payload"]["action"] == "start"
        assert args[1]["payload"]["parameters"] == {"range": 32}

    def test_config_summary(self, workflow):
        """Test _config_summary returns correct dictionary."""
        workflow.config = WorkflowConfig({
            "x": 10, "z": 20, "range": 64,
            "template": "Tower",
            "miner.strategy": "grid",
        })
        
        summary = workflow._config_summary()
        
        assert summary["x"] == 10
        assert summary["z"] == 20
        assert summary["range"] == 64
        assert summary["template"] == "Tower"
        assert summary["miner_strategy"] == "grid"

    def test_log(self, workflow, mock_workspace):
        """Test _log calls workspace log_event."""
        workflow.state = WorkflowState(current_stage=2)
        workflow._log("TEST_EVENT", {"key": "value"})
        
        mock_workspace.log_event.assert_called_once()
        args = mock_workspace.log_event.call_args[0]
        assert args[0] == "WORKFLOW_TEST_EVENT"
        assert args[1] == "Workflow"
        assert args[2]["stage"] == 2
        assert args[2]["key"] == "value"


class TestWorkflowAsync:
    """Async tests for Workflow class."""

    @pytest.fixture
    def mock_mc(self):
        """Create mock Minecraft connection."""
        mc = MagicMock()
        mc.postToChat = MagicMock()
        return mc

    @pytest.fixture
    def mock_workspace(self):
        """Create mock SharedWorkspace."""
        workspace = MagicMock()
        workspace.register_workflow_observer = MagicMock()
        workspace.post_command = MagicMock()
        workspace.log_event = MagicMock()
        return workspace

    @pytest.fixture
    def mock_agents(self):
        """Create mock agent instances."""
        class MockExplorer:
            pass
        class MockMiner:
            pass
        class MockBuilder:
            pass
        
        explorer = MockExplorer()
        explorer.__class__.__name__ = "ExplorerBot"
        miner = MockMiner()
        miner.__class__.__name__ = "MinerBot"
        builder = MockBuilder()
        builder.__class__.__name__ = "BuilderBot"
        
        return [explorer, miner, builder]

    @pytest.fixture
    def workflow(self, mock_mc, mock_workspace, mock_agents):
        """Create Workflow instance with mocks."""
        return Workflow(mock_mc, mock_workspace, mock_agents)

    @pytest.mark.asyncio
    async def test_run_already_running(self, workflow, mock_mc):
        """Test that run returns early if already running."""
        workflow.is_running = True
        
        await workflow.run({})
        
        mock_mc.postToChat.assert_called_with("Workflow is already running")

    @pytest.mark.asyncio
    async def test_process_messages_updates_state(self, workflow):
        """Test that _process_messages updates state from queue."""
        workflow.message_queue.put_nowait({"type": "map.v1", "payload": {}})
        workflow.message_queue.put_nowait({
            "type": "materials.requirements.v1",
            "payload": {}
        })
        
        await workflow._process_messages()
        
        assert workflow.state.exploration_complete is True
        assert workflow.state.materials_requested is True
        assert workflow.message_queue.empty()

    @pytest.mark.asyncio
    async def test_process_messages_empty_queue(self, workflow):
        """Test _process_messages with empty queue."""
        initial_state = workflow.state
        
        await workflow._process_messages()
        
        # State should not be modified
        assert workflow.state.exploration_complete == initial_state.exploration_complete

    @pytest.mark.asyncio
    async def test_stage_exploration(self, workflow, mock_workspace, mock_mc):
        """Test _stage_exploration sends correct command."""
        workflow.config = WorkflowConfig({"x": 10, "z": 20, "range": 64})
        workflow.state = WorkflowState()
        
        await workflow._stage_exploration()
        
        mock_workspace.post_command.assert_called()
        call_args = mock_workspace.post_command.call_args[0]
        assert call_args[0] == "ExplorerBot"
        assert call_args[1]["payload"]["action"] == "start"
        assert call_args[1]["payload"]["parameters"]["range"] == 64

    @pytest.mark.asyncio
    async def test_stage_planning(self, workflow, mock_workspace, mock_mc):
        """Test _stage_planning sends correct command."""
        workflow.config = WorkflowConfig({"template": "ModernHouse"})
        workflow.state = WorkflowState()
        
        await workflow._stage_planning()
        
        mock_workspace.post_command.assert_called()
        call_args = mock_workspace.post_command.call_args[0]
        assert call_args[0] == "BuilderBot"
        assert call_args[1]["payload"]["action"] == "plan"
        assert call_args[1]["payload"]["parameters"]["set"] == "ModernHouse"

    @pytest.mark.asyncio
    async def test_stage_building(self, workflow, mock_workspace, mock_mc):
        """Test _stage_building sends correct command."""
        workflow.config = WorkflowConfig({})
        workflow.state = WorkflowState()
        
        await workflow._stage_building()
        
        mock_workspace.post_command.assert_called()
        call_args = mock_workspace.post_command.call_args[0]
        assert call_args[0] == "BuilderBot"
        assert call_args[1]["payload"]["action"] == "build"

    @pytest.mark.asyncio
    async def test_wait_for_condition_met_immediately(self, workflow):
        """Test _wait_for when condition is already met."""
        workflow.config = WorkflowConfig({})
        
        # Condition that is immediately true
        await workflow._wait_for(lambda: True, 10.0, "Test")
        
        # Should complete without timeout

    @pytest.mark.asyncio
    async def test_wait_for_should_stop(self, workflow):
        """Test _wait_for raises CancelledError when should_stop is True."""
        workflow.should_stop = True
        
        with pytest.raises(asyncio.CancelledError):
            await workflow._wait_for(lambda: False, 10.0, "Test")


class TestMessageHandlersMapping:
    """Tests for MESSAGE_HANDLERS dictionary."""

    def test_all_handlers_registered(self):
        """Test that all expected handlers are in MESSAGE_HANDLERS."""
        expected_types = [
            "map.v1",
            "materials.requirements.v1",
            "inventory.v1",
            "build.v1",
        ]
        for msg_type in expected_types:
            assert msg_type in MESSAGE_HANDLERS

    def test_handlers_are_callable(self):
        """Test that all handlers are callable."""
        for handler in MESSAGE_HANDLERS.values():
            assert callable(handler)
