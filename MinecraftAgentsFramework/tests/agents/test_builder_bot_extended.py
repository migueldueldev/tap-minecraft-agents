"""
Extended unit tests for BuilderBot.

This module provides comprehensive coverage for BuilderBot functionality including:
- Schematic loading
- Bill of Materials computation
- Material management
- Build position finding
- Message handling
- Build execution
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
from agents.builder_bot import BuilderBot
from base_agent import AgentState


@pytest.fixture
def mock_mc():
    """Create a mock Minecraft connection."""
    mc = MagicMock()
    mc.setBlock = MagicMock()
    mc.postToChat = MagicMock()
    return mc


@pytest.fixture
def mock_workspace():
    """Create a mock workspace."""
    workspace = MagicMock()
    workspace.log_event = MagicMock()
    workspace.post_message = MagicMock()
    return workspace


@pytest.fixture
def builder_bot(mock_mc, mock_workspace):
    """Create a BuilderBot instance."""
    return BuilderBot(mock_mc, mock_workspace)


class TestBuilderBotInitialization:
    """Tests for BuilderBot initialization."""

    def test_initial_state(self, builder_bot):
        """Test initial bot state."""
        assert builder_bot.current_plan is None
        assert builder_bot.structured_blocks == {}
        assert builder_bot.bom == {}
        assert builder_bot.inventory == {}
        assert builder_bot.build_position is None
        assert builder_bot.is_building is False
        assert builder_bot.build_ready is False

    def test_checkpoint_initial(self, builder_bot):
        """Test initial checkpoint state."""
        assert builder_bot.checkpoint == {"layer": 0, "block_idx": 0}

    def test_terrain_data_initial(self, builder_bot):
        """Test terrain data starts as None."""
        assert builder_bot.terrain_data is None


class TestBillOfMaterials:
    """Tests for Bill of Materials functionality."""

    def test_compute_bom_empty(self, builder_bot):
        """Test computing BOM with no blocks."""
        builder_bot.structured_blocks = {}
        
        bom = builder_bot._compute_bom()
        
        assert bom == {}

    def test_compute_bom_single_layer(self, builder_bot):
        """Test computing BOM with single layer."""
        builder_bot.structured_blocks = {
            0: [
                {"x": 0, "z": 0, "block": "STONE", "data": 0},
                {"x": 1, "z": 0, "block": "STONE", "data": 0},
                {"x": 0, "z": 1, "block": "GLASS", "data": 0}
            ]
        }
        
        bom = builder_bot._compute_bom()
        
        assert bom == {"STONE": 2, "GLASS": 1}

    def test_compute_bom_multiple_layers(self, builder_bot):
        """Test computing BOM with multiple layers."""
        builder_bot.structured_blocks = {
            0: [{"x": 0, "z": 0, "block": "STONE", "data": 0}],
            1: [{"x": 0, "z": 0, "block": "STONE", "data": 0}],
            2: [{"x": 0, "z": 0, "block": "WOOD", "data": 0}]
        }
        
        bom = builder_bot._compute_bom()
        
        assert bom == {"STONE": 2, "WOOD": 1}


class TestPendingMaterials:
    """Tests for pending materials calculation."""

    def test_pending_materials_all_pending(self, builder_bot):
        """Test pending materials when nothing collected."""
        builder_bot.bom = {"STONE": 10, "IRON_ORE": 5}
        builder_bot.inventory = {}
        
        pending = builder_bot._pending_materials()
        
        assert pending == {"STONE": 10, "IRON_ORE": 5}

    def test_pending_materials_partial(self, builder_bot):
        """Test pending materials with partial collection."""
        builder_bot.bom = {"STONE": 10, "IRON_ORE": 5}
        builder_bot.inventory = {"STONE": 6}
        
        pending = builder_bot._pending_materials()
        
        assert pending == {"STONE": 4, "IRON_ORE": 5}

    def test_pending_materials_complete(self, builder_bot):
        """Test pending materials when all collected."""
        builder_bot.bom = {"STONE": 10}
        builder_bot.inventory = {"STONE": 10}
        
        pending = builder_bot._pending_materials()
        
        assert pending == {}

    def test_pending_materials_auto_provided(self, builder_bot):
        """Test that auto-provided materials are excluded."""
        builder_bot.bom = {"STONE": 10, "DIRT": 5, "GRASS": 3}
        builder_bot.inventory = {}
        
        pending = builder_bot._pending_materials()
        
        assert "STONE" in pending
        assert "DIRT" not in pending
        assert "GRASS" not in pending

    def test_pending_materials_excess(self, builder_bot):
        """Test pending materials with excess inventory."""
        builder_bot.bom = {"STONE": 10}
        builder_bot.inventory = {"STONE": 15}
        
        pending = builder_bot._pending_materials()
        
        assert pending == {}


class TestMaterialsReady:
    """Tests for materials ready check."""

    def test_materials_ready_true(self, builder_bot):
        """Test materials ready when all collected."""
        builder_bot.bom = {"STONE": 10, "IRON_ORE": 5}
        builder_bot.inventory = {"STONE": 10, "IRON_ORE": 5}
        
        assert builder_bot._materials_ready() is True

    def test_materials_ready_false(self, builder_bot):
        """Test materials ready when incomplete."""
        builder_bot.bom = {"STONE": 10}
        builder_bot.inventory = {"STONE": 5}
        
        assert builder_bot._materials_ready() is False

    def test_materials_ready_empty_bom(self, builder_bot):
        """Test materials ready with empty BOM."""
        builder_bot.bom = {}
        builder_bot.inventory = {}
        
        assert builder_bot._materials_ready() is True


class TestFindBuildPosition:
    """Tests for build position finding."""

    def test_find_build_position_no_terrain(self, builder_bot):
        """Test finding position with no terrain data."""
        builder_bot.terrain_data = None
        builder_bot.structured_blocks = {0: [{"x": 0, "z": 0, "block": "STONE"}]}
        
        pos = builder_bot._find_build_position()
        
        assert pos is None

    def test_find_build_position_no_blocks(self, builder_bot):
        """Test finding position with no structured blocks."""
        builder_bot.terrain_data = {"regions": [{"width": 10, "depth": 10, "y": 64, "blocks": [{"x": 0, "z": 0}]}]}
        builder_bot.structured_blocks = {}
        
        pos = builder_bot._find_build_position()
        
        assert pos is None

    def test_find_build_position_no_regions(self, builder_bot):
        """Test finding position with no regions."""
        builder_bot.terrain_data = {"regions": []}
        builder_bot.structured_blocks = {0: [{"x": 0, "z": 0, "block": "STONE"}]}
        
        pos = builder_bot._find_build_position()
        
        assert pos is None

    def test_find_build_position_success(self, builder_bot):
        """Test finding valid build position."""
        builder_bot.terrain_data = {
            "regions": [
                {"width": 10, "depth": 10, "y": 64, "blocks": [{"x": 100, "z": 100}]}
            ]
        }
        builder_bot.structured_blocks = {
            0: [{"x": 0, "z": 0, "block": "STONE"}, {"x": 1, "z": 1, "block": "STONE"}]
        }
        
        pos = builder_bot._find_build_position()
        
        assert pos == (100, 64, 100)

    def test_find_build_position_smallest_fitting(self, builder_bot):
        """Test that smallest fitting region is selected."""
        builder_bot.terrain_data = {
            "regions": [
                {"width": 20, "depth": 20, "y": 64, "blocks": [{"x": 0, "z": 0}]},
                {"width": 5, "depth": 5, "y": 65, "blocks": [{"x": 50, "z": 50}]},
                {"width": 1, "depth": 1, "y": 66, "blocks": [{"x": 100, "z": 100}]}
            ]
        }
        builder_bot.structured_blocks = {
            0: [{"x": 0, "z": 0, "block": "STONE"}, {"x": 2, "z": 2, "block": "STONE"}]
        }
        
        pos = builder_bot._find_build_position()
        
        # Should select 5x5 region as 3x3 structure fits but not in 1x1
        assert pos == (50, 65, 50)


class TestBuilderPerceive:
    """Tests for BuilderBot perceive method."""

    @pytest.mark.asyncio
    async def test_perceive_map_message(self, builder_bot, mock_mc):
        """Test perceive processes map message."""
        builder_bot.get_messages = MagicMock(return_value=[{
            "type": "map.v1",
            "payload": {"regions": [{"width": 10, "depth": 10}]}
        }])
        
        await builder_bot.perceive()
        
        assert builder_bot.terrain_data == {"regions": [{"width": 10, "depth": 10}]}
        mock_mc.postToChat.assert_called()

    @pytest.mark.asyncio
    async def test_perceive_inventory_message(self, builder_bot, mock_mc):
        """Test perceive processes inventory message."""
        builder_bot.bom = {"IRON_ORE": 10}
        builder_bot.get_messages = MagicMock(return_value=[{
            "type": "inventory.v1",
            "payload": {
                "materials": [{"material": "IRON_ORE", "collected": 5}],
                "complete": False
            }
        }])
        
        await builder_bot.perceive()
        
        assert builder_bot.inventory["IRON_ORE"] == 5

    @pytest.mark.asyncio
    async def test_perceive_inventory_complete(self, builder_bot, mock_mc):
        """Test perceive handles complete inventory."""
        builder_bot.bom = {"IRON_ORE": 5}
        builder_bot.get_messages = MagicMock(return_value=[{
            "type": "inventory.v1",
            "payload": {
                "materials": [{"material": "IRON_ORE", "collected": 5}],
                "complete": True
            }
        }])
        
        await builder_bot.perceive()
        
        mock_mc.postToChat.assert_called()


class TestBuilderDecide:
    """Tests for BuilderBot decide method."""

    @pytest.mark.asyncio
    async def test_decide_no_plan(self, builder_bot):
        """Test decide with no plan."""
        builder_bot.current_plan = None
        builder_bot.state = AgentState.RUNNING
        builder_bot.set_state = MagicMock()
        
        await builder_bot.decide()
        
        builder_bot.set_state.assert_called()

    @pytest.mark.asyncio
    async def test_decide_waiting_materials(self, builder_bot):
        """Test decide sets waiting state when materials needed."""
        builder_bot.current_plan = "test_house"
        builder_bot.bom = {"DIAMOND_ORE": 10}
        builder_bot.inventory = {}
        builder_bot.set_state = MagicMock()
        
        await builder_bot.decide()
        
        builder_bot.set_state.assert_called_with(AgentState.WAITING, "Waiting materials for building")

    @pytest.mark.asyncio
    async def test_decide_ready_to_build(self, builder_bot):
        """Test decide sets running state when ready to build."""
        builder_bot.current_plan = "test_house"
        builder_bot.bom = {"STONE": 10}
        builder_bot.inventory = {"STONE": 10}
        builder_bot.build_ready = True
        builder_bot.is_building = False
        builder_bot.state = AgentState.IDLE
        builder_bot.set_state = MagicMock()
        
        await builder_bot.decide()
        
        builder_bot.set_state.assert_called_with(AgentState.RUNNING, "Ready to build the structure")


class TestBuilderAct:
    """Tests for BuilderBot act method."""

    @pytest.mark.asyncio
    async def test_act_not_ready(self, builder_bot):
        """Test act does nothing when not ready."""
        builder_bot.build_ready = False
        
        await builder_bot.act()
        
        # Should just sleep, no building

    @pytest.mark.asyncio
    async def test_act_already_building(self, builder_bot):
        """Test act does nothing when already building."""
        builder_bot.build_ready = True
        builder_bot.is_building = True
        
        await builder_bot.act()
        
        # Should not start another build


class TestBuilderCommands:
    """Tests for BuilderBot command handling."""

    def test_handle_command_bom_no_plan(self, builder_bot, mock_mc):
        """Test BOM command with no plan."""
        builder_bot.bom = {}
        
        builder_bot.handle_command({"payload": {"action": "bom", "parameters": {}}})
        
        mock_mc.postToChat.assert_called()

    def test_handle_command_plan_list(self, builder_bot, mock_mc):
        """Test plan list command."""
        with patch.object(BuilderBot, "_discover_plans", return_value=["Castle", "Tower", "House"]):
            builder_bot.handle_command({"payload": {"action": "plan", "parameters": {"list": True}}})
        
        # Should post each plan name
        assert mock_mc.postToChat.call_count >= 3


class TestCheckpoint:
    """Tests for checkpoint functionality."""

    def test_save_checkpoint(self, builder_bot, mock_workspace):
        """Test saving build checkpoint."""
        builder_bot.current_plan = "Tower"
        builder_bot.checkpoint = {"layer": 2, "block_idx": 5}
        builder_bot.inventory = {"STONE": 10}
        
        builder_bot._save_checkpoint()
        
        mock_workspace.log_event.assert_called()
        call_args = mock_workspace.log_event.call_args
        assert call_args[0][0] == "CHECKPOINT"


class TestPublishRequirements:
    """Tests for publishing requirements."""

    def test_publish_requirements_no_pending(self, builder_bot, mock_workspace):
        """Test publish requirements with nothing pending."""
        builder_bot.bom = {"STONE": 10}
        builder_bot.inventory = {"STONE": 10}
        
        builder_bot._publish_requirements()
        
        mock_workspace.post_message.assert_not_called()

    def test_publish_requirements_already_published(self, builder_bot, mock_mc):
        """Test publish requirements when already published."""
        builder_bot.bom = {"STONE": 10}
        builder_bot.inventory = {}
        builder_bot.requirements_published = True
        
        builder_bot._publish_requirements()
        
        mock_mc.postToChat.assert_called()

    def test_publish_requirements_success(self, builder_bot, mock_workspace, mock_mc):
        """Test successful requirements publishing."""
        builder_bot.bom = {"IRON_ORE": 10}
        builder_bot.inventory = {}
        builder_bot.requirements_published = False
        builder_bot.terrain_data = {"regions": [{"width": 10, "depth": 10, "y": 64, "blocks": [{"x": 0, "z": 0}]}]}
        builder_bot.structured_blocks = {0: [{"x": 0, "z": 0, "block": "STONE"}]}
        builder_bot.pda_task = MagicMock()
        builder_bot.state = AgentState.WAITING
        
        builder_bot._publish_requirements()
        
        mock_workspace.post_message.assert_called()
        assert builder_bot.requirements_published is True


class TestPublishProgress:
    """Tests for publishing build progress."""

    def test_publish_progress_in_progress(self, builder_bot, mock_workspace):
        """Test publishing in-progress status."""
        builder_bot.structured_blocks = {
            0: [{"x": 0, "z": 0, "block": "STONE"}],
            1: [{"x": 0, "z": 0, "block": "STONE"}]
        }
        builder_bot.checkpoint = {"layer": 0, "block_idx": 1}
        builder_bot.current_plan = "Tower"
        builder_bot.pda_task = MagicMock()
        builder_bot.state = AgentState.RUNNING
        
        builder_bot._publish_progress("IN_PROGRESS")
        
        mock_workspace.post_message.assert_called()

    def test_publish_progress_completed(self, builder_bot, mock_workspace):
        """Test publishing completed status."""
        builder_bot.structured_blocks = {0: [{"x": 0, "z": 0, "block": "STONE"}]}
        builder_bot.checkpoint = {"layer": 1, "block_idx": 0}
        builder_bot.current_plan = "Tower"
        builder_bot.pda_task = MagicMock()
        builder_bot.state = AgentState.RUNNING
        
        builder_bot._publish_progress("COMPLETED")
        
        mock_workspace.post_message.assert_called()


class TestDiscoverPlans:
    """Tests for plan discovery."""

    def test_discover_plans_empty_dir(self, builder_bot):
        """Test discovering plans in empty directory."""
        with patch('os.path.exists', return_value=False):
            plans = BuilderBot._discover_plans()
        
        assert plans == []

    def test_discover_plans_with_files(self, builder_bot):
        """Test discovering plans with schematic files."""
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=["Tower.schem", "House.schem", "readme.txt"]):
                plans = BuilderBot._discover_plans()
        
        assert "Tower" in plans
        assert "House" in plans
        assert "readme" not in plans


class TestBlockMap:
    """Tests for block mapping."""

    def test_block_map_contains_common_blocks(self, builder_bot):
        """Test block map contains common blocks."""
        assert 0 in BuilderBot.BLOCK_MAP  # AIR
        assert 1 in BuilderBot.BLOCK_MAP  # STONE
        assert 4 in BuilderBot.BLOCK_MAP  # COBBLESTONE
        assert 56 in BuilderBot.BLOCK_MAP  # DIAMOND_ORE

    def test_auto_provided_contains_materials(self, builder_bot):
        """Test auto-provided set contains expected materials."""
        assert "DIRT" in BuilderBot.AUTO_PROVIDED
        assert "GRASS" in BuilderBot.AUTO_PROVIDED
        assert "WOOD" in BuilderBot.AUTO_PROVIDED
        assert "TORCH" in BuilderBot.AUTO_PROVIDED
