"""
Unit tests for the Utils module.

This module tests utility functions used throughout the framework including:
- Message creation and validation
- Command building
- Parameter parsing
- Agent finding
- Message parsing
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from utils import (
    create_message,
    create_command,
    validate_message,
    parse_parameters,
    find_agent,
    handle_workflow_command,
    parse_message,
    MESSAGE_SCHEMA
)


class TestCreateMessage:
    """Tests for the create_message function."""

    def test_create_message_basic(self):
        """Test creating a basic message with required fields."""
        msg = create_message("test.v1", "SourceBot", "TargetBot", {"data": "value"})
        
        assert msg["type"] == "test.v1"
        assert msg["source"] == "SourceBot"
        assert msg["target"] == "TargetBot"
        assert msg["payload"] == {"data": "value"}
        assert msg["status"] == "SUCCESS"
        assert "timestamp" in msg
        assert "id" in msg

    def test_create_message_with_custom_status(self):
        """Test creating a message with custom status."""
        msg = create_message("test.v1", "Source", "Target", {}, status="PENDING")
        assert msg["status"] == "PENDING"

    def test_create_message_with_context(self):
        """Test creating a message with context information."""
        context = {"task_id": "12345", "state": "RUNNING"}
        msg = create_message("test.v1", "Source", "Target", {}, context=context)
        
        assert "context" in msg
        assert msg["context"]["task_id"] == "12345"
        assert msg["context"]["state"] == "RUNNING"

    def test_create_message_timestamp_format(self):
        """Test that timestamp follows ISO 8601 format with Z suffix."""
        msg = create_message("test.v1", "Source", "Target", {})
        
        assert msg["timestamp"].endswith("Z")
        # Should be parseable as ISO format
        ts = msg["timestamp"].rstrip("Z")
        datetime.fromisoformat(ts)

    def test_create_message_generates_unique_ids(self):
        """Test that each message gets a unique ID."""
        msg1 = create_message("test.v1", "Source", "Target", {})
        msg2 = create_message("test.v1", "Source", "Target", {})
        
        assert msg1["id"] != msg2["id"]


class TestCreateCommand:
    """Tests for the create_command function."""

    def test_create_command_basic(self):
        """Test creating a basic command."""
        cmd = create_command("User", "ExplorerBot", "start", {"x": 10, "z": 20})
        
        assert cmd["type"] == "command.control.v1"
        assert cmd["source"] == "User"
        assert cmd["target"] == "ExplorerBot"
        assert cmd["payload"]["action"] == "start"
        assert cmd["payload"]["parameters"] == {"x": 10, "z": 20}

    def test_create_command_with_context(self):
        """Test creating a command with context."""
        context = {"task_id": "abc123"}
        cmd = create_command("User", "MinerBot", "stop", {}, context=context)
        
        assert "context" in cmd
        assert cmd["context"]["task_id"] == "abc123"

    def test_create_command_empty_parameters(self):
        """Test creating a command with empty parameters."""
        cmd = create_command("User", "BuilderBot", "status", {})
        
        assert cmd["payload"]["parameters"] == {}


class TestValidateMessage:
    """Tests for the validate_message function."""

    def test_validate_valid_message(self):
        """Test validating a correctly structured message."""
        message = {
            "type": "test.v1",
            "source": "Agent",
            "target": "Target",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {},
            "status": "SUCCESS"
        }
        
        result = validate_message(message)
        assert result is True

    def test_validate_message_missing_required_field(self):
        """Test that validation fails when required field is missing."""
        message = {
            "type": "test.v1",
            "source": "Agent",
            # Missing target
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {},
            "status": "SUCCESS"
        }
        
        with pytest.raises(Exception):
            validate_message(message)

    def test_validate_message_invalid_status(self):
        """Test that validation fails with invalid status."""
        message = {
            "type": "test.v1",
            "source": "Agent",
            "target": "Target",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {},
            "status": "INVALID_STATUS"
        }
        
        with pytest.raises(Exception):
            validate_message(message)

    def test_validate_message_all_valid_statuses(self):
        """Test that all valid statuses pass validation."""
        valid_statuses = ["SUCCESS", "PENDING", "FAILED", "COMPLETED", "IN_PROGRESS"]
        
        for status in valid_statuses:
            message = {
                "type": "test.v1",
                "source": "Agent",
                "target": "Target",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {},
                "status": status
            }
            result = validate_message(message)
            assert result is True


class TestParseParameters:
    """Tests for the parse_parameters function."""

    def test_parse_empty_parameters(self):
        """Test parsing empty parameter list."""
        result = parse_parameters([])
        assert result == {}

    def test_parse_key_equals_value_integer(self):
        """Test parsing key=value with integer value."""
        result = parse_parameters(["x=100"])
        assert result["x"] == 100

    def test_parse_key_equals_value_float(self):
        """Test parsing key=value with float value."""
        result = parse_parameters(["speed=1.5"])
        assert result["speed"] == 1.5

    def test_parse_key_equals_value_string(self):
        """Test parsing key=value with string value."""
        result = parse_parameters(["template=Tower"])
        assert result["template"] == "Tower"

    def test_parse_key_value_separate(self):
        """Test parsing 'key value' as separate parameters."""
        result = parse_parameters(["strategy", "vertical"])
        assert result["strategy"] == "vertical"

    def test_parse_standalone_flag(self):
        """Test parsing a standalone flag at the end."""
        result = parse_parameters(["list"])
        assert result["list"] is None

    def test_parse_mixed_formats(self):
        """Test parsing a mix of formats."""
        result = parse_parameters(["x=50", "template", "House", "verbose"])
        
        assert result["x"] == 50
        assert result["template"] == "House"
        assert result["verbose"] is None

    def test_parse_negative_numbers(self):
        """Test parsing negative integer values."""
        result = parse_parameters(["offset=-10"])
        assert result["offset"] == -10

    def test_parse_float_with_negative(self):
        """Test parsing negative float values."""
        result = parse_parameters(["multiplier=-2.5"])
        assert result["multiplier"] == -2.5


class TestFindAgent:
    """Tests for the find_agent function."""

    def test_find_agent_exists(self):
        """Test finding an existing agent by class name."""
        class TestAgent:
            pass
        
        agent = TestAgent()
        instances = [agent]
        
        result = find_agent(instances, "TestAgent")
        assert result is agent

    def test_find_agent_not_exists(self):
        """Test finding an agent that doesn't exist."""
        result = find_agent([], "NonExistentBot")
        assert result is None

    def test_find_agent_multiple_instances(self):
        """Test finding agent among multiple instances."""
        class AgentA:
            pass
        class AgentB:
            pass
        
        agent_a = AgentA()
        agent_b = AgentB()
        instances = [agent_a, agent_b]
        
        result = find_agent(instances, "AgentB")
        assert result is agent_b

    def test_find_agent_case_sensitive(self):
        """Test that agent search is case-sensitive."""
        class TestBot:
            pass
        
        agent = TestBot()
        instances = [agent]
        
        result = find_agent(instances, "testbot")
        assert result is None


class TestHandleWorkflowCommand:
    """Tests for the handle_workflow_command function."""

    @pytest.mark.asyncio
    async def test_handle_run_command(self):
        """Test handling workflow run command."""
        workflow = MagicMock()
        workflow.run = AsyncMock()
        mc = MagicMock()
        workspace = MagicMock()
        
        await handle_workflow_command("run", ["x=10", "z=20"], workflow, mc, workspace, [])
        
        workflow.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_stop_command(self):
        """Test handling workflow stop command."""
        workflow = MagicMock()
        mc = MagicMock()
        workspace = MagicMock()
        
        await handle_workflow_command("stop", [], workflow, mc, workspace, [])
        
        workflow.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_help_command(self):
        """Test handling workflow help command."""
        workflow = MagicMock()
        mc = MagicMock()
        workspace = MagicMock()
        
        await handle_workflow_command("help", [], workflow, mc, workspace, [])
        
        workflow.help.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_invalid_command(self):
        """Test handling invalid workflow command."""
        workflow = MagicMock()
        mc = MagicMock()
        workspace = MagicMock()
        
        await handle_workflow_command("invalid", [], workflow, mc, workspace, [])
        
        mc.postToChat.assert_called()


class TestParseMessage:
    """Tests for the parse_message function."""

    @pytest.mark.asyncio
    async def test_parse_valid_explorer_command(self):
        """Test parsing a valid explorer command message."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        
        class MockExplorer:
            pass
        explorer = MockExplorer()
        explorer.__class__.__name__ = "ExplorerBot"
        instances = [explorer]
        
        await parse_message("./explorer start x=10 z=20", mc, workspace, instances, workflow)
        
        workspace.post_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_valid_miner_command(self):
        """Test parsing a valid miner command message."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        
        class MockMiner:
            pass
        miner = MockMiner()
        miner.__class__.__name__ = "MinerBot"
        instances = [miner]
        
        await parse_message("./miner start strategy=grid", mc, workspace, instances, workflow)
        
        workspace.post_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_unknown_agent(self):
        """Test parsing command for unknown agent."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        
        await parse_message("./unknown start", mc, workspace, [], workflow)
        
        mc.postToChat.assert_called()

    @pytest.mark.asyncio
    async def test_parse_invalid_action(self):
        """Test parsing command with invalid action."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        
        class MockExplorer:
            pass
        explorer = MockExplorer()
        explorer.__class__.__name__ = "ExplorerBot"
        instances = [explorer]
        
        await parse_message("./explorer invalid_action", mc, workspace, instances, workflow)
        
        mc.postToChat.assert_called()

    @pytest.mark.asyncio
    async def test_parse_non_command_message(self):
        """Test parsing a message that is not a command."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        
        await parse_message("hello world", mc, workspace, [], workflow)
        
        # Should not call any command methods
        workspace.post_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_workflow_command(self):
        """Test parsing a workflow command."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        workflow.run = AsyncMock()
        
        await parse_message("./workflow run template=Tower", mc, workspace, [], workflow)
        
        # Workflow run should be called via asyncio task
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_parse_agent_not_found(self):
        """Test parsing command when agent instance is not found."""
        mc = MagicMock()
        workspace = MagicMock()
        workflow = MagicMock()
        
        await parse_message("./explorer start", mc, workspace, [], workflow)
        
        mc.postToChat.assert_called()
