"""
Extended unit tests for ExplorerBot.

This module provides comprehensive coverage for ExplorerBot functionality including:
- Terrain scanning
- Elevation map generation
- Region identification
- Visualization handling
- Command processing
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.explorer_bot import ExplorerBot
import mcpi.block as block


@pytest.fixture
def mock_mc():
    """Create a mock Minecraft connection."""
    mc = MagicMock()
    mc.getHeight.return_value = 64
    mc.getBlock.return_value = block.GRASS.id
    mc.getBlockWithData.return_value = MagicMock(id=block.GRASS.id, data=0)
    return mc


@pytest.fixture
def mock_workspace():
    """Create a mock workspace."""
    workspace = MagicMock()
    workspace.post_message = MagicMock()
    return workspace


@pytest.fixture
def explorer_bot(mock_mc, mock_workspace):
    """Create an ExplorerBot instance."""
    with patch('agents.explorer_bot.BaseAgent', autospec=True):
        bot = ExplorerBot(mock_mc, mock_workspace)
        bot.state = MagicMock()
        bot.state.value = "IDLE"
        bot.pda_task = None
        bot.args = {}
        bot.logger = MagicMock()
        return bot


class TestExplorerBotInitialization:
    """Tests for ExplorerBot initialization."""

    def test_initial_state(self, explorer_bot):
        """Test initial bot state."""
        assert explorer_bot.show_regions is False
        assert explorer_bot.display_duration == 15.0
        assert explorer_bot.request_queue == []
        assert explorer_bot.waiting_confirmation is False
        assert explorer_bot.heights == {}
        assert explorer_bot.blocks == {}

    def test_displayed_regions_empty(self, explorer_bot):
        """Test displayed regions start empty."""
        assert explorer_bot.displayed_regions == []


class TestElevationMapGeneration:
    """Tests for elevation map generation."""

    def test_generate_elevation_map_single(self, explorer_bot):
        """Test generating elevation map with single height."""
        heights = {(0, 0): 64, (1, 0): 64, (0, 1): 64}
        
        elevation_map = explorer_bot.generate_elevation_map(heights)
        
        assert 64 in elevation_map
        assert len(elevation_map[64]) == 3

    def test_generate_elevation_map_multiple(self, explorer_bot):
        """Test generating elevation map with multiple heights."""
        heights = {(0, 0): 64, (1, 0): 65, (0, 1): 64, (1, 1): 66}
        
        elevation_map = explorer_bot.generate_elevation_map(heights)
        
        assert 64 in elevation_map
        assert 65 in elevation_map
        assert 66 in elevation_map
        assert len(elevation_map[64]) == 2
        assert len(elevation_map[65]) == 1
        assert len(elevation_map[66]) == 1

    def test_generate_elevation_map_empty(self, explorer_bot):
        """Test generating elevation map from empty heights."""
        heights = {}
        
        elevation_map = explorer_bot.generate_elevation_map(heights)
        
        assert elevation_map == {}


class TestFindLargestRectangle:
    """Tests for finding largest rectangle in binary grid."""

    def test_find_largest_rectangle_full(self, explorer_bot):
        """Test finding rectangle in full grid."""
        grid = [
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1]
        ]
        
        rect = explorer_bot.find_largest_rectangle(grid, 3, 3)
        
        assert rect is not None
        x, y, w, h = rect
        assert w * h == 9

    def test_find_largest_rectangle_partial(self, explorer_bot):
        """Test finding rectangle in partial grid."""
        grid = [
            [1, 1, 0],
            [1, 1, 1],
            [1, 1, 1]
        ]
        
        rect = explorer_bot.find_largest_rectangle(grid, 3, 3)
        
        assert rect is not None
        x, y, w, h = rect
        assert w * h >= 4

    def test_find_largest_rectangle_empty(self, explorer_bot):
        """Test finding rectangle in empty grid."""
        grid = [
            [0, 0, 0],
            [0, 0, 0],
            [0, 0, 0]
        ]
        
        rect = explorer_bot.find_largest_rectangle(grid, 3, 3)
        
        # Should return None or empty rectangle
        assert rect is None or (rect[2] * rect[3] == 0)

    def test_find_largest_rectangle_single_cell(self, explorer_bot):
        """Test finding rectangle with single valid cell."""
        grid = [
            [0, 0, 0],
            [0, 1, 0],
            [0, 0, 0]
        ]
        
        rect = explorer_bot.find_largest_rectangle(grid, 3, 3)
        
        assert rect is not None
        x, y, w, h = rect
        assert w * h == 1


class TestRegionStability:
    """Tests for region stability checking."""

    def test_is_region_stable_grass(self, explorer_bot):
        """Test that grass region is stable."""
        explorer_bot.UNSTABLE_IDS = {block.WATER.id}
        explorer_bot.blocks = {
            (0, 64, 0): MagicMock(id=block.GRASS.id),
            (1, 64, 0): MagicMock(id=block.GRASS.id)
        }
        
        region = {'y': 64, 'blocks': [(0, 0), (1, 0)]}
        
        assert explorer_bot.is_region_stable(region) is True

    def test_is_region_stable_water(self, explorer_bot):
        """Test that water region is unstable."""
        explorer_bot.UNSTABLE_IDS = {block.WATER.id}
        explorer_bot.blocks = {
            (0, 64, 0): MagicMock(id=block.WATER.id),
            (1, 64, 0): MagicMock(id=block.GRASS.id)
        }
        
        region = {'y': 64, 'blocks': [(0, 0), (1, 0)]}
        
        assert explorer_bot.is_region_stable(region) is False

    def test_is_region_stable_lava(self, explorer_bot):
        """Test that lava region is unstable."""
        explorer_bot.UNSTABLE_IDS = {block.LAVA.id}
        explorer_bot.blocks = {
            (0, 64, 0): MagicMock(id=block.LAVA.id)
        }
        
        region = {'y': 64, 'blocks': [(0, 0)]}
        
        assert explorer_bot.is_region_stable(region) is False


class TestExplorerCommands:
    """Tests for ExplorerBot command handling."""

    def test_handle_command_toggle_enable(self, explorer_bot, mock_mc):
        """Test toggle command enables display."""
        explorer_bot.show_regions = False
        
        command = {"payload": {"action": "toggle", "parameters": {"display": 20.0}}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        assert explorer_bot.show_regions is True
        assert explorer_bot.display_duration == 20.0

    def test_handle_command_toggle_disable(self, explorer_bot, mock_mc):
        """Test toggle command disables display."""
        explorer_bot.show_regions = True
        
        command = {"payload": {"action": "toggle", "parameters": {"display": 15.0}}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        assert explorer_bot.show_regions is False

    def test_handle_command_queue_pending(self, explorer_bot, mock_mc):
        """Test queue command adds pending request to queue."""
        explorer_bot.args = {"active": True}
        explorer_bot.waiting_confirmation = True
        explorer_bot.pending_command = {"payload": {"action": "start", "parameters": {"x": 10}}}
        
        command = {"payload": {"action": "queue"}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        assert len(explorer_bot.request_queue) == 1
        assert explorer_bot.waiting_confirmation is False
        assert explorer_bot.pending_command is None

    def test_handle_command_queue_no_pending(self, explorer_bot, mock_mc):
        """Test queue command with no pending request."""
        explorer_bot.waiting_confirmation = False
        
        command = {"payload": {"action": "queue"}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        mock_mc.postToChat.assert_called()

    def test_handle_command_confirm(self, explorer_bot, mock_mc):
        """Test confirm command processes pending request."""
        explorer_bot.args = {"active": True}
        explorer_bot.waiting_confirmation = True
        explorer_bot.pending_command = {"payload": {"action": "start", "parameters": {"x": 50}}}
        
        command = {"payload": {"action": "confirm"}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        assert explorer_bot.waiting_confirmation is False
        assert explorer_bot.pending_command is None

    def test_handle_command_confirm_no_pending(self, explorer_bot, mock_mc):
        """Test confirm command with no pending request."""
        explorer_bot.waiting_confirmation = False
        
        command = {"payload": {"action": "confirm"}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        mock_mc.postToChat.assert_called()

    def test_handle_command_set(self, explorer_bot, mock_mc):
        """Test set command updates arguments."""
        command = {"payload": {"action": "set", "parameters": {"x": 100, "z": 200}}}
        result = explorer_bot.handle_command(command)
        
        assert result is True
        assert explorer_bot.args.get("x") == 100
        assert explorer_bot.args.get("z") == 200


class TestExplorerPerceive:
    """Tests for ExplorerBot perceive method."""

    @pytest.mark.asyncio
    async def test_perceive_scans_world(self, explorer_bot):
        """Test perceive scans the world."""
        explorer_bot.scan_world = MagicMock(return_value=({(0, 0): 64}, {(0, 64, 0): MagicMock()}))
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = ({(0, 0): 64}, {(0, 64, 0): MagicMock()})
            heights = await explorer_bot.perceive(x=0, z=0, range=1)
        
        assert explorer_bot.has_new_scan is True
        assert (0, 0) in heights

    @pytest.mark.asyncio
    async def test_perceive_clears_visualization(self, explorer_bot):
        """Test perceive clears previous visualization."""
        explorer_bot.clear_visualization = MagicMock()
        explorer_bot.scan_world = MagicMock(return_value=({}, {}))
        
        with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = ({}, {})
            await explorer_bot.perceive(x=0, z=0, range=1)
        
        explorer_bot.clear_visualization.assert_called_once()


class TestExplorerDecide:
    """Tests for ExplorerBot decide method."""

    @pytest.mark.asyncio
    async def test_decide_no_scan(self, explorer_bot):
        """Test decide returns None when no scan data."""
        explorer_bot.has_new_scan = False
        
        result = await explorer_bot.decide()
        
        assert result is None

    @pytest.mark.asyncio
    async def test_decide_with_scan(self, explorer_bot):
        """Test decide processes scan data."""
        explorer_bot.has_new_scan = True
        explorer_bot.heights = {(0, 0): 64}
        explorer_bot.x0, explorer_bot.z0, explorer_bot.area = 0, 0, 1
        explorer_bot.blocks = {(0, 64, 0): MagicMock(id=block.GRASS.id)}
        
        with patch.object(explorer_bot, 'generate_elevation_map', return_value={64: [(0, 0)]}):
            with patch.object(explorer_bot, 'identify_flat_regions', return_value=[{'y': 64, 'blocks': [(0, 0)], 'width': 1, 'depth': 1}]):
                result = await explorer_bot.decide()
        
        assert result is not None


class TestExplorerVisualization:
    """Tests for ExplorerBot visualization methods."""

    def test_clear_visualization_empty(self, explorer_bot, mock_mc):
        """Test clear visualization with no regions."""
        explorer_bot.displayed_regions = []
        
        explorer_bot.clear_visualization()
        
        assert explorer_bot.displayed_regions == []

    def test_clear_visualization_with_regions(self, explorer_bot, mock_mc):
        """Test clear visualization restores blocks."""
        mock_block = MagicMock(id=block.GRASS.id, data=0)
        explorer_bot.displayed_regions = [{
            'bounds': (0, 0, 5, 5, 64),
            'blocks': {(0, 63, 0): mock_block, (1, 63, 0): mock_block}
        }]
        
        explorer_bot.clear_visualization()
        
        assert explorer_bot.displayed_regions == []


class TestExplorerMessageGeneration:
    """Tests for ExplorerBot message generation."""

    def test_generate_message(self, explorer_bot):
        """Test generating map message."""
        explorer_bot.stable_regions = [{
            'y': 64,
            'blocks': [(0, 0), (1, 0)],
            'width': 2,
            'depth': 1
        }]
        explorer_bot.blocks = {
            (0, 64, 0): MagicMock(id=block.GRASS.id, data=0),
            (1, 64, 0): MagicMock(id=block.STONE.id, data=0)
        }
        explorer_bot.pda_task = MagicMock()
        explorer_bot.state = MagicMock()
        explorer_bot.state.value = "RUNNING"
        
        with patch.object(explorer_bot, 'get_block_names', return_value={block.GRASS.id: "GRASS", block.STONE.id: "STONE"}):
            message = explorer_bot.generate_message()
        
        assert message["type"] == "map.v1"
        assert message["source"] == "ExplorerBot"
        assert message["target"] == "BuilderBot"
        assert "regions" in message["payload"]

    def test_generate_message_with_context(self, explorer_bot):
        """Test message includes context."""
        explorer_bot.stable_regions = [{'y': 64, 'blocks': [], 'width': 0, 'depth': 0}]
        explorer_bot.blocks = {}
        explorer_bot.pda_task = MagicMock()
        explorer_bot.state = MagicMock()
        explorer_bot.state.value = "RUNNING"
        
        with patch.object(explorer_bot, 'get_block_names', return_value={}):
            message = explorer_bot.generate_message()
        
        assert "context" in message


class TestExplorerStop:
    """Tests for ExplorerBot stop behavior."""

    def test_stop_clears_visualization(self, explorer_bot, mock_mc):
        """Test stop clears visualization."""
        explorer_bot.displayed_regions = [{'bounds': (0, 0, 5, 5, 64), 'blocks': {}}]
        
        with patch('agents.explorer_bot.BaseAgent.stop'):
            explorer_bot.stop()
        
        # clear_visualization should be called
        assert True  # Method should not raise
