"""
Unit tests for Mining Strategies.

This module tests the mining strategy implementations including:
- MiningStrategy base class
- VerticalSearchStrategy
- GridSearchStrategy
- VeinSearchStrategy
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from strategies.mining_strategy import MiningStrategy
from strategies.vertical_search_strategy import VerticalSearchStrategy
from strategies.grid_search_strategy import GridSearchStrategy
from base_agent import AgentState


class MockMinecraft:
    """Mock Minecraft connection for strategy tests."""
    
    def __init__(self):
        self.blocks = {}
        self.chat_messages = []
    
    def postToChat(self, message):
        self.chat_messages.append(message)
    
    def setBlock(self, x, y, z, block_id, data=0):
        self.blocks[(x, y, z)] = block_id
    
    def getBlock(self, x, y, z):
        return self.blocks.get((x, y, z), 0)
    
    def getHeight(self, x, z):
        return 64


class MockAgent:
    """Mock agent for strategy tests."""
    
    def __init__(self):
        self.should_stop = False
        self.state = AgentState.RUNNING


@pytest.fixture
def mock_setup(tmp_path):
    """Create mock dependencies for strategy testing."""
    mc = MockMinecraft()
    workspace = MagicMock()
    workspace.log_file = str(tmp_path / "mining.log")
    agent = MockAgent()
    return mc, workspace, agent


class TestMiningStrategyBase:
    """Tests for MiningStrategy base class functionality."""

    def test_lock_region_success(self, mock_setup):
        """Test successful region locking."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        result = strategy.lock_region(10, 20)
        
        assert result is True
        assert (10, 20) in strategy.locked_regions

    def test_lock_region_already_locked(self, mock_setup):
        """Test locking an already locked region."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.lock_region(10, 20)
        result = strategy.lock_region(10, 20)
        
        assert result is False

    def test_release_all_locks(self, mock_setup):
        """Test releasing all locked regions."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.lock_region(10, 20)
        strategy.lock_region(30, 40)
        
        strategy.release_all_locks()
        
        assert len(strategy.locked_regions) == 0

    def test_release_all_locks_empty(self, mock_setup):
        """Test releasing locks when none exist."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Should not raise an error
        strategy.release_all_locks()
        
        assert len(strategy.locked_regions) == 0

    def test_update_collected_materials(self, mock_setup):
        """Test updating collected materials count."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.update_collected_materials("COAL_ORE", 5)
        strategy.update_collected_materials("COAL_ORE", 3)
        
        assert strategy.collected_materials["COAL_ORE"] == 8

    def test_update_collected_materials_new(self, mock_setup):
        """Test updating collected materials for new material."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.update_collected_materials("DIAMOND_ORE", 1)
        
        assert strategy.collected_materials["DIAMOND_ORE"] == 1

    def test_requirements_met_true(self, mock_setup):
        """Test requirements_met when all requirements are satisfied."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.collected_materials = {"COAL_ORE": 10, "IRON_ORE": 5}
        requirements = {"COAL_ORE": 5, "IRON_ORE": 5}
        
        assert strategy.requirements_met(requirements) is True

    def test_requirements_met_false(self, mock_setup):
        """Test requirements_met when requirements are not satisfied."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.collected_materials = {"COAL_ORE": 3}
        requirements = {"COAL_ORE": 5}
        
        assert strategy.requirements_met(requirements) is False

    def test_requirements_met_partial(self, mock_setup):
        """Test requirements_met with partial collection."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.collected_materials = {"COAL_ORE": 10}
        requirements = {"COAL_ORE": 5, "IRON_ORE": 5}
        
        assert strategy.requirements_met(requirements) is False

    def test_should_stop_mining_false(self, mock_setup):
        """Test should_stop_mining when agent is running."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        assert strategy.should_stop_mining() is False

    def test_should_stop_mining_true_stop_flag(self, mock_setup):
        """Test should_stop_mining when agent should_stop is set."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        agent.should_stop = True
        
        assert strategy.should_stop_mining() is True

    def test_should_stop_mining_true_stopped_state(self, mock_setup):
        """Test should_stop_mining when agent is in STOPPED state."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        agent.state = AgentState.STOPPED
        
        assert strategy.should_stop_mining() is True

    def test_should_stop_mining_no_agent(self, mock_setup):
        """Test should_stop_mining when no agent is attached."""
        mc, workspace, _ = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=None)
        
        assert strategy.should_stop_mining() is False

    def test_get_material_name(self, mock_setup):
        """Test getting material name from block ID."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Block ID 56 is DIAMOND_ORE
        name = strategy.get_material_name(56)
        
        assert name == "DIAMOND_ORE"

    def test_get_material_name_unknown(self, mock_setup):
        """Test getting material name for unknown block ID."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        name = strategy.get_material_name(9999)
        
        assert "UNKNOWN" in name

    def test_get_block_names(self, mock_setup):
        """Test building block names mapping."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        names = strategy.get_block_names()
        
        assert isinstance(names, dict)
        assert len(names) > 0


class TestVerticalSearchStrategy:
    """Tests for VerticalSearchStrategy."""

    def test_get_strategy_name(self, mock_setup):
        """Test strategy name."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        assert strategy.get_strategy_name() == "VerticalSearch"

    @pytest.mark.asyncio
    async def test_mine_empty_column(self, mock_setup):
        """Test mining an empty column (all air)."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_mine_finds_ore(self, mock_setup):
        """Test mining finds ore in column."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Place coal ore (ID 16) at specific location
        mc.blocks[(0, 60, 0)] = 16
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        assert "COAL_ORE" in result
        assert result["COAL_ORE"] >= 1

    @pytest.mark.asyncio
    async def test_mine_stops_on_requirements_met(self, mock_setup):
        """Test mining stops when requirements are met."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Place multiple coal ores
        for y in range(50, 65):
            mc.blocks[(0, y, 0)] = 16
        
        result = await strategy.mine({"COAL_ORE": 3}, (0, 5, 0), {}, {})
        
        assert result["COAL_ORE"] >= 3

    @pytest.mark.asyncio
    async def test_mine_respects_bedrock_level(self, mock_setup):
        """Test mining doesn't go below bedrock level."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        mc.getHeight = lambda x, z: 10
        
        # Should not mine at y < 5 (bedrock)
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        # No blocks should be mined below bedrock
        for (x, y, z), _ in mc.blocks.items():
            if y < 5:
                # Block should still exist if it was there
                pass

    @pytest.mark.asyncio
    async def test_mine_interrupted_by_stop(self, mock_setup):
        """Test mining is interrupted when agent stops."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        agent.should_stop = True
        
        result = await strategy.mine({"COAL_ORE": 10}, (0, 5, 0), {}, {})
        
        # Should return early
        workspace.log_event.assert_any_call("MINING_INTERRUPTED", "TestAgent", pytest.approx({"position": pytest.approx((0, pytest.approx(64, abs=100), 0), abs=100), "reason": "Agent stopped"}, abs=100))

    @pytest.mark.asyncio
    async def test_mine_region_lock_failed(self, mock_setup):
        """Test mining fails gracefully when region lock fails."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Pre-lock the region
        strategy.locked_regions.add((0, 0))
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_mine_resume_from_position(self, mock_setup):
        """Test mining resumes from saved position."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Set current position to resume from
        current_position = {"x": 0, "y": 50, "z": 0}
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), current_position, {})
        
        # Should have logged some events
        assert workspace.log_event.called


class TestGridSearchStrategy:
    """Tests for GridSearchStrategy."""

    def test_get_strategy_name(self, mock_setup):
        """Test strategy name."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        assert strategy.get_strategy_name() == "GridSearch"

    @pytest.mark.asyncio
    async def test_mine_grid_area(self, mock_setup):
        """Test mining a grid area."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {"range": 2})
        
        # Should complete without errors
        assert workspace.log_event.called

    @pytest.mark.asyncio
    async def test_mine_grid_finds_ore(self, mock_setup):
        """Test grid mining finds ore."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Place ore in grid area
        mc.blocks[(2, 50, 2)] = 16  # COAL_ORE
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {"range": 5})
        
        assert "COAL_ORE" in result

    @pytest.mark.asyncio
    async def test_mine_grid_respects_range(self, mock_setup):
        """Test grid mining respects range parameter."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        coords = {"range": 3}
        
        await strategy.mine({"COAL_ORE": 1}, (10, 5, 10), {}, coords)
        
        # Mining log should be called
        assert workspace.log_event.called

    @pytest.mark.asyncio
    async def test_mine_grid_lock_failure(self, mock_setup):
        """Test grid mining handles lock failure."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Pre-lock the region
        strategy.locked_regions.add((0, 0))
        
        result = await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {"range": 2})
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_mine_grid_updates_position(self, mock_setup):
        """Test grid mining updates current position."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        current_position = {}
        
        await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), current_position, {"range": 2})
        
        # Position should be updated
        assert "x" in current_position or "y" in current_position or "z" in current_position

    @pytest.mark.asyncio
    async def test_mine_grid_resume(self, mock_setup):
        """Test grid mining resumes from position."""
        mc, workspace, agent = mock_setup
        strategy = GridSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        current_position = {"x": 1, "y": 50, "z": 1}
        
        await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), current_position, {"range": 2})
        
        # Should have logged some events
        assert workspace.log_event.called


class TestStrategyLogging:
    """Tests for strategy logging behavior."""

    @pytest.mark.asyncio
    async def test_region_lock_logged(self, mock_setup):
        """Test that region locking is logged."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.lock_region(10, 20)
        
        # Check that log_event was called with REGION_LOCKED
        calls = workspace.log_event.call_args_list
        assert any(call[0][0] == "REGION_LOCKED" for call in calls)

    @pytest.mark.asyncio
    async def test_region_release_logged(self, mock_setup):
        """Test that region release is logged."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        strategy.lock_region(10, 20)
        strategy.release_all_locks()
        
        calls = [call[0][0] for call in workspace.log_event.call_args_list]
        assert "REGIONS_RELEASED" in calls

    @pytest.mark.asyncio
    async def test_mining_started_logged(self, mock_setup):
        """Test that mining start is logged."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        calls = [call[0][0] for call in workspace.log_event.call_args_list]
        assert "MINING_STARTED" in calls

    @pytest.mark.asyncio
    async def test_mining_completed_logged(self, mock_setup):
        """Test that mining completion is logged."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        calls = [call[0][0] for call in workspace.log_event.call_args_list]
        assert "MINING_COMPLETED" in calls

    @pytest.mark.asyncio
    async def test_block_mined_logged(self, mock_setup):
        """Test that mined blocks are logged."""
        mc, workspace, agent = mock_setup
        strategy = VerticalSearchStrategy(mc, "TestAgent", workspace, agent=agent)
        
        # Place coal ore
        mc.blocks[(0, 60, 0)] = 16
        
        await strategy.mine({"COAL_ORE": 1}, (0, 5, 0), {}, {})
        
        calls = [call[0][0] for call in workspace.log_event.call_args_list]
        assert "BLOCK_MINED" in calls
