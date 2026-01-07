import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from main import parse_message, parse_parameters, find_agent


class TestParseParameters:
    """Tests for the parse_parameters function"""
    
    def test_parse_key_value_with_equals(self):
        """Test parsing key=value format"""
        result = parse_parameters(["speed=10", "range=5.5", "name=test"])
        assert result["speed"] == 10
        assert result["range"] == 5.5
        assert result["name"] == "test"
    
    def test_parse_key_value_pairs(self):
        """Test parsing key value pairs without equals"""
        result = parse_parameters(["target", "diamond", "depth", "10"])
        assert result["target"] == "diamond"
        assert result["depth"] == 10
    
    def test_parse_flag_only(self):
        """Test parsing standalone flags (last parameter without value)"""
        # Only the last parameter without a value is treated as a flag
        result = parse_parameters(["verbose"])
        assert result["verbose"] is None
    
    def test_parse_consecutive_words_as_key_value(self):
        """Test that consecutive words are treated as key-value pairs"""
        result = parse_parameters(["fast", "verbose"])
        # First word is key and second is value
        assert result["fast"] == "verbose"
    
    def test_parse_mixed_parameters(self):
        """Test parsing mixed parameter formats"""
        result = parse_parameters(["range=5", "target", "gold", "fast"])
        assert result["range"] == 5
        assert result["target"] == "gold"
        assert result["fast"] is None


class TestFindAgent:
    """Tests for the find_agent function"""
    
    def test_find_existing_agent(self):
        """Test finding an agent that exists"""
        class MockAgent:
            pass
        agent = MockAgent()
        agent.__class__.__name__ = "TestBot"
        instances = [agent]
        
        result = find_agent(instances, "TestBot")
        assert result is agent
    
    def test_find_nonexistent_agent(self):
        """Test finding an agent that doesn't exist"""
        result = find_agent([], "MissingBot")
        assert result is None


@pytest.mark.asyncio
async def test_parse_message_success():
    """Test parsing a valid command message"""
    # Setup mocks
    mc = MagicMock()
    workspace = MagicMock()
    
    class MockBot:
        pass
    
    explorer_instance = MockBot()
    explorer_instance.__class__.__name__ = "ExplorerBot"
    instances = [explorer_instance]
    
    # Test valid command
    await parse_message("./explorer start speed=10", mc, workspace, instances)
    
    # Verify that post command was called with correct data
    workspace.post_command.assert_called_once()
    args, _ = workspace.post_command.call_args
    assert args[0] == "ExplorerBot"
    assert args[1]["payload"]["action"] == "start"
    assert args[1]["payload"]["parameters"]["speed"] == 10


@pytest.mark.asyncio
async def test_parse_message_invalid_agent():
    """Test that unrecognized agents are handled with an error message"""
    mc = MagicMock()
    workspace = MagicMock()
    instances = []
    
    await parse_message("./unknown_agent start", mc, workspace, instances)
    
    mc.postToChat.assert_called_with('Agent "unknown_agent" not recognized')


@pytest.mark.asyncio
async def test_parse_message_instance_not_found():
    """Test that missing agent instances are handled"""
    mc = MagicMock()
    workspace = MagicMock()
    instances = []  # No instances loaded
    
    await parse_message("./explorer start", mc, workspace, instances)
    
    mc.postToChat.assert_called_with('Agent instance "ExplorerBot" not found')


@pytest.mark.asyncio
async def test_parse_message_invalid_action():
    """Test that invalid actions are rejected"""
    mc = MagicMock()
    workspace = MagicMock()
    
    class MockBot:
        pass
    
    explorer_instance = MockBot()
    explorer_instance.__class__.__name__ = "ExplorerBot"
    instances = [explorer_instance]
    
    await parse_message("./explorer fly", mc, workspace, instances)
    
    mc.postToChat.assert_called_with('Action "fly" not valid for agent "explorer"')


@pytest.mark.asyncio
async def test_parse_message_complex_parameters():
    """Test parsing complex parameter combinations"""
    mc = MagicMock()
    workspace = MagicMock()
    
    class MockBot:
        pass
    
    miner_instance = MockBot()
    miner_instance.__class__.__name__ = "MinerBot"
    instances = [miner_instance]
    
    # Test different parameter formats: key=val, key val and flag
    await parse_message("./miner start range=5 target diamond fast", mc, workspace, instances)
    
    workspace.post_command.assert_called_once()
    payload = workspace.post_command.call_args[0][1]["payload"]
    params = payload["parameters"]
    
    assert params["range"] == 5
    assert params["target"] == "diamond"
    assert params["fast"] is None


@pytest.mark.asyncio
async def test_parse_message_non_command():
    """Test that non-command messages are ignored"""
    mc = MagicMock()
    workspace = MagicMock()
    instances = []
    
    # Regular chat message without ./ prefix
    await parse_message("Hello world", mc, workspace, instances)
    
    # Nothing should be called
    workspace.post_command.assert_not_called()
    mc.postToChat.assert_not_called()


@pytest.mark.asyncio
async def test_parse_message_builder_bot():
    """Test parsing command for BuilderBot"""
    mc = MagicMock()
    workspace = MagicMock()
    
    class MockBot:
        pass
    
    builder_instance = MockBot()
    builder_instance.__class__.__name__ = "BuilderBot"
    instances = [builder_instance]
    
    await parse_message("./builder plan list", mc, workspace, instances)
    
    workspace.post_command.assert_called_once()
    args, _ = workspace.post_command.call_args
    assert args[0] == "BuilderBot"
    assert args[1]["payload"]["action"] == "plan"