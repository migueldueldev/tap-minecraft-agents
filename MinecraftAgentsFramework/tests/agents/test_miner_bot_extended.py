"""
Extended unit tests for MinerBot.

This module provides comprehensive coverage for MinerBot functionality including:
- Strategy loading
- Material requirements handling
- Ore to block conversion
- Inventory management
- Mining coordination
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.miner_bot import MinerBot, AUTO_PROVIDED_MATERIALS, MINABLE_MATERIALS, PROCESSABLE_MATERIALS
from base_agent import AgentState


class MockPos:
    """Mock position object."""
    def __init__(self, x=0, y=64, z=0):
        self.x = x
        self.y = y
        self.z = z


@pytest.fixture
def mock_mc():
    """Create a mock Minecraft connection."""
    mc = MagicMock()
    mc.player.getTilePos.return_value = MockPos(10, 64, 30)
    mc.getHeight.return_value = 64
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
def miner_bot(mock_mc, mock_workspace):
    """Create a MinerBot instance."""
    with patch.object(MinerBot, 'load_strategies', return_value={
        'vertical': MagicMock(),
        'grid': MagicMock(),
        'vein': MagicMock()
    }):
        bot = MinerBot(mock_mc, mock_workspace)
        return bot


class TestMinerBotInitialization:
    """Tests for MinerBot initialization."""

    def test_initial_state(self, miner_bot):
        """Test initial bot state."""
        assert miner_bot.inventory == {}
        assert miner_bot.mining_strategy_name == ""
        assert miner_bot.material_requirements == {}
        assert miner_bot.is_mining is False
        assert miner_bot.ready_to_mine is False

    def test_strategy_map_loaded(self, miner_bot):
        """Test strategy map is populated."""
        assert "vertical" in miner_bot.strategy_map
        assert "grid" in miner_bot.strategy_map
        assert "vein" in miner_bot.strategy_map


class TestMaterialConstants:
    """Tests for material constant definitions."""

    def test_auto_provided_materials(self):
        """Test auto-provided materials list."""
        assert "DIRT" in AUTO_PROVIDED_MATERIALS
        assert "GRASS" in AUTO_PROVIDED_MATERIALS
        assert "COBBLESTONE" in AUTO_PROVIDED_MATERIALS

    def test_minable_materials(self):
        """Test minable materials list."""
        assert "STONE" in MINABLE_MATERIALS
        assert "COAL_ORE" in MINABLE_MATERIALS
        assert "IRON_ORE" in MINABLE_MATERIALS
        assert "DIAMOND_ORE" in MINABLE_MATERIALS

    def test_processable_materials(self):
        """Test processable materials mapping."""
        assert "IRON_BLOCK" in PROCESSABLE_MATERIALS
        assert PROCESSABLE_MATERIALS["IRON_BLOCK"]["raw"] == "IRON_ORE"
        assert PROCESSABLE_MATERIALS["IRON_BLOCK"]["amount"] == 9


class TestMaterialRequirements:
    """Tests for material requirements handling."""

    def test_handle_material_requirements_auto_provide(self, miner_bot):
        """Test auto-provided materials are added to inventory."""
        message = {
            "source": "BuilderBot",
            "payload": {
                "requirements": {
                    "COBBLESTONE": 10,
                    "IRON_ORE": 5
                }
            }
        }
        
        miner_bot.handle_material_requirements(message)
        
        assert miner_bot.inventory["COBBLESTONE"] == 10
        assert "IRON_ORE" not in miner_bot.inventory or miner_bot.inventory.get("IRON_ORE", 0) == 0

    def test_handle_material_requirements_minable(self, miner_bot):
        """Test minable requirements are tracked."""
        message = {
            "source": "BuilderBot",
            "payload": {
                "requirements": {
                    "IRON_ORE": 5,
                    "DIAMOND_ORE": 2
                }
            }
        }
        
        miner_bot.handle_material_requirements(message)
        
        assert miner_bot.material_requirements["IRON_ORE"] == 5
        assert miner_bot.material_requirements["DIAMOND_ORE"] == 2

    def test_handle_material_requirements_with_reference(self, miner_bot):
        """Test reference position is captured."""
        message = {
            "source": "BuilderBot",
            "payload": {
                "requirements": {"STONE": 10},
                "reference_position": (100, 64, 200)
            }
        }
        
        miner_bot.handle_material_requirements(message)
        
        assert miner_bot.reference_position == (100, 64, 200)


class TestMinableRequirements:
    """Tests for get_minable_requirements method."""

    def test_get_minable_requirements_direct(self, miner_bot):
        """Test direct ore requirements."""
        miner_bot.material_requirements = {"IRON_ORE": 10}
        miner_bot.inventory = {}
        
        reqs = miner_bot.get_minable_requirements()
        
        assert reqs["IRON_ORE"] == 10

    def test_get_minable_requirements_block_conversion(self, miner_bot):
        """Test block requirements convert to ore needs."""
        miner_bot.material_requirements = {"IRON_BLOCK": 1}
        miner_bot.inventory = {}
        
        reqs = miner_bot.get_minable_requirements()
        
        assert reqs["IRON_ORE"] == 9

    def test_get_minable_requirements_partial_inventory(self, miner_bot):
        """Test partial inventory reduces requirements."""
        miner_bot.material_requirements = {"IRON_ORE": 10}
        miner_bot.inventory = {"IRON_ORE": 3}
        
        reqs = miner_bot.get_minable_requirements()
        
        assert reqs["IRON_ORE"] == 7


class TestOreToBlockConversion:
    """Tests for ore to block conversion."""

    def test_convert_ores_to_blocks_exact(self, miner_bot):
        """Test exact conversion with no remainder."""
        miner_bot.material_requirements = {"IRON_BLOCK": 1}
        miner_bot.inventory = {"IRON_ORE": 9}
        
        miner_bot.convert_ores_to_blocks()
        
        assert miner_bot.inventory["IRON_BLOCK"] == 1
        assert miner_bot.inventory["IRON_ORE"] == 0

    def test_convert_ores_to_blocks_remainder(self, miner_bot):
        """Test conversion with remainder."""
        miner_bot.material_requirements = {"IRON_BLOCK": 2}
        miner_bot.inventory = {"IRON_ORE": 20}
        
        miner_bot.convert_ores_to_blocks()
        
        assert miner_bot.inventory["IRON_BLOCK"] == 2
        assert miner_bot.inventory["IRON_ORE"] == 2

    def test_convert_ores_to_blocks_insufficient(self, miner_bot):
        """Test conversion with insufficient ores."""
        miner_bot.material_requirements = {"IRON_BLOCK": 2}
        miner_bot.inventory = {"IRON_ORE": 5}
        
        miner_bot.convert_ores_to_blocks()
        
        # Should not create any blocks
        assert miner_bot.inventory.get("IRON_BLOCK", 0) == 0


class TestRequirementsFulfilled:
    """Tests for requirements_fulfilled method."""

    def test_requirements_fulfilled_true(self, miner_bot):
        """Test requirements fulfilled when complete."""
        miner_bot.material_requirements = {"STONE": 5, "IRON_ORE": 3}
        miner_bot.inventory = {"STONE": 5, "IRON_ORE": 3}
        
        assert miner_bot.requirements_fulfilled() is True

    def test_requirements_fulfilled_false(self, miner_bot):
        """Test requirements not fulfilled when incomplete."""
        miner_bot.material_requirements = {"STONE": 5}
        miner_bot.inventory = {"STONE": 2}
        
        assert miner_bot.requirements_fulfilled() is False

    def test_requirements_fulfilled_excess(self, miner_bot):
        """Test requirements fulfilled with excess."""
        miner_bot.material_requirements = {"STONE": 5}
        miner_bot.inventory = {"STONE": 10}
        
        assert miner_bot.requirements_fulfilled() is True

    def test_requirements_fulfilled_empty(self, miner_bot):
        """Test empty requirements are fulfilled."""
        miner_bot.material_requirements = {}
        miner_bot.inventory = {}
        
        assert miner_bot.requirements_fulfilled() is True


class TestMinerCommands:
    """Tests for MinerBot command handling."""

    def test_handle_command_set_strategy(self, miner_bot):
        """Test set strategy command."""
        command = {"payload": {"action": "set", "parameters": {"strategy": "grid"}}}
        
        miner_bot.handle_command(command)
        
        assert miner_bot.mining_strategy_name == "grid"

    def test_handle_command_fulfill(self, miner_bot):
        """Test fulfill command."""
        command = {"payload": {"action": "fulfill"}}
        miner_bot.ready_to_mine = False
        
        miner_bot.handle_command(command)
        
        assert miner_bot.ready_to_mine is True


class TestMinerSetState:
    """Tests for MinerBot set_state overrides."""

    def test_set_state_error_releases_locks(self, miner_bot, mock_workspace):
        """Test ERROR state releases mining locks."""
        miner_bot.state = AgentState.RUNNING
        mock_strategy = MagicMock()
        miner_bot.mining_strategy = mock_strategy
        
        miner_bot.set_state(AgentState.ERROR, reason="Test Error")
        
        assert miner_bot.state == AgentState.ERROR
        mock_strategy.release_all_locks.assert_called_once()

    def test_set_state_running_no_lock_release(self, miner_bot, mock_workspace):
        """Test RUNNING state does not release locks."""
        miner_bot.state = AgentState.IDLE
        mock_strategy = MagicMock()
        miner_bot.mining_strategy = mock_strategy
        
        miner_bot.set_state(AgentState.RUNNING, reason="Starting")
        
        mock_strategy.release_all_locks.assert_not_called()

    def test_set_state_stopped_releases_locks(self, miner_bot, mock_workspace):
        """Test STOPPED state releases mining locks."""
        miner_bot.state = AgentState.RUNNING
        mock_strategy = MagicMock()
        miner_bot.mining_strategy = mock_strategy
        
        miner_bot.set_state(AgentState.STOPPED, reason="Stopping")
        
        mock_strategy.release_all_locks.assert_called_once()


class TestMinerPerceive:
    """Tests for MinerBot perceive method."""

    @pytest.mark.asyncio
    async def test_perceive_updates_coords(self, miner_bot, mock_mc):
        """Test perceive updates coordinates."""
        mock_mc.player.getTilePos.return_value = MockPos(1, 2, 3)
        mock_mc.getHeight.return_value = 64
        
        coords = await miner_bot.perceive()
        
        assert coords["x"] == 1
        assert coords["z"] == 3

    @pytest.mark.asyncio
    async def test_perceive_with_explicit_coords(self, miner_bot, mock_mc):
        """Test perceive uses explicit coordinates."""
        mock_mc.getHeight.return_value = 64
        mock_mc.player.getTilePos.return_value = MockPos(0, 0, 0)
        # Initialize direction_x as the code expects it to be set in certain paths
        miner_bot.direction_x = 1
        
        coords = await miner_bot.perceive(x=100, z=200)
        
        assert coords["x"] == 100
        assert coords["z"] == 200

    @pytest.mark.asyncio
    async def test_perceive_processes_messages(self, miner_bot, mock_mc):
        """Test perceive processes material requirement messages."""
        miner_bot.get_messages = MagicMock(return_value=[{
            "type": "materials.requirements.v1",
            "source": "BuilderBot",
            "payload": {"requirements": {"STONE": 10}}
        }])
        mock_mc.getHeight.return_value = 64
        
        await miner_bot.perceive()
        
        assert miner_bot.material_requirements == {"STONE": 10}

    @pytest.mark.asyncio
    async def test_perceive_surface_check(self, miner_bot, mock_mc):
        """Test perceive checks surface level."""
        mock_mc.getHeight.return_value = 10
        miner_bot.set_state = MagicMock()
        
        await miner_bot.perceive(y=50)  # Target above surface
        
        # Should set ERROR state
        miner_bot.set_state.assert_called()


class TestMinerDecide:
    """Tests for MinerBot decide method."""

    @pytest.mark.asyncio
    async def test_decide_no_bom(self, miner_bot):
        """Test decide with no BOM."""
        miner_bot.current_bom = None
        miner_bot.state = AgentState.RUNNING
        miner_bot.set_state = MagicMock()
        
        await miner_bot.decide()
        
        # Should set IDLE
        miner_bot.set_state.assert_called()

    @pytest.mark.asyncio
    async def test_decide_selects_strategy(self, miner_bot):
        """Test decide selects mining strategy."""
        miner_bot.current_bom = {"IRON_ORE": 10}
        miner_bot.mining_strategy_name = "vertical"
        miner_bot.mining_strategy = None
        miner_bot.ready_to_mine = True
        miner_bot.set_state = MagicMock()
        
        mock_strategy_class = MagicMock()
        mock_strategy_class.__name__ = "VerticalSearchStrategy"
        miner_bot.strategy_map = {"vertical": mock_strategy_class}
        
        await miner_bot.decide()
        
        # Strategy should be instantiated
        mock_strategy_class.assert_called()


class TestSendInventoryUpdate:
    """Tests for inventory update publishing."""

    def test_send_inventory_update_partial(self, miner_bot, mock_workspace):
        """Test sending partial inventory update."""
        miner_bot.material_requirements = {"IRON_ORE": 10}
        miner_bot.inventory = {"IRON_ORE": 5}
        miner_bot.pda_task = MagicMock()
        miner_bot.state = AgentState.RUNNING
        
        miner_bot.send_inventory_update(complete=False)
        
        mock_workspace.post_message.assert_called()

    def test_send_inventory_update_complete(self, miner_bot, mock_workspace):
        """Test sending complete inventory update."""
        miner_bot.material_requirements = {"IRON_ORE": 10}
        miner_bot.inventory = {"IRON_ORE": 10}
        miner_bot.pda_task = MagicMock()
        miner_bot.state = AgentState.RUNNING
        
        miner_bot.send_inventory_update(complete=True)
        
        mock_workspace.post_message.assert_called()
        call_args = mock_workspace.post_message.call_args
        assert call_args[0][0]["payload"]["complete"] is True


class TestBlockNames:
    """Tests for block name retrieval."""

    def test_get_block_names(self, miner_bot):
        """Test getting block names mapping."""
        names = miner_bot.get_block_names()
        
        assert isinstance(names, dict)
        assert len(names) > 0


class TestMinerReferencePosition:
    """Tests for reference position handling."""

    @pytest.mark.asyncio
    async def test_perceive_with_reference_position(self, miner_bot, mock_mc):
        """Test perceive uses reference position."""
        miner_bot.reference_position = (100, 64, 200)
        miner_bot.mining_strategy_name = "vertical"
        mock_mc.getHeight.return_value = 64
        
        coords = await miner_bot.perceive()
        
        # Should apply offset from reference
        assert coords["x"] != 100  # Offset applied

    @pytest.mark.asyncio
    async def test_perceive_reference_grid_offset(self, miner_bot, mock_mc):
        """Test perceive applies grid strategy offset."""
        miner_bot.reference_position = (100, 64, 200)
        miner_bot.mining_strategy_name = "grid"
        miner_bot.kwargs_strategy = "grid"
        mock_mc.getHeight.return_value = 64
        miner_bot.get_messages = MagicMock(return_value=[])
        
        coords = await miner_bot.perceive(range=32)
        
        # Grid should have larger offset
        mock_mc.postToChat.assert_called()
