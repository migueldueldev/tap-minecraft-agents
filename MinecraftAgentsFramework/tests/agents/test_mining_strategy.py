import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from strategies.VeinSearchStrategy import VeinSearchStrategy

@pytest.fixture
def mock_dependencies():
    mc = MagicMock()
    workspace = MagicMock()
    agent = MagicMock()
    agent.should_stop = False
    
    # Return a standard surface level
    mc.getHeight.return_value = 10
    # Return air by default
    mc.getBlock.return_value = 0
    
    return mc, workspace, agent

@pytest.mark.asyncio
async def test_vein_search_strategy_name(mock_dependencies):
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    assert strategy.get_strategy_name() == "VeinSearch"

@pytest.mark.asyncio
async def test_mine_starts_and_completes_empty(mock_dependencies):
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    
    # Target Y is higher than surface
    requirements = {"DIAMOND": 1}
    result = await strategy.mine(requirements, (0, 15, 0), {}, {})
    
    assert result == {}
    ws.log_event.assert_any_call("MINING_STARTED", "test_agent", ANY)
    ws.log_event.assert_any_call("MINING_COMPLETED", "test_agent", ANY)

@pytest.mark.asyncio
async def test_mine_interrupted_by_agent_stop(mock_dependencies):
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    
    agent.should_stop = True
    requirements = {"GOLD_ORE": 1}
    
    await strategy.mine(requirements, (0, 5, 0), {}, {})
    
    # Verify interruption log
    interruption_logged = any(call[0][0] == "MINING_INTERRUPTED" for call in ws.log_event.call_args_list)
    assert interruption_logged

@pytest.mark.asyncio
async def test_mine_finds_and_processes_vein(mock_dependencies):
    """Test that the strategy finds and mines ore veins"""
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    
    # Block ID 56 is DIAMOND_ORE
    target_block_id = 56
    material_name = strategy.get_material_name(target_block_id)
    
    # Return default surface level
    mc.getHeight.return_value = 10
    
    # Setup mock to return diamond ore on specific blocks during staircase mining
    # Vein search strategy uses a staircase pattern starting from initial height going down
    def get_block_side_effect(x, y, z):
        # Return diamond ore at position (0, 10, 0)
        if x == 0 and y == 10 and z == 0:
            return target_block_id
        return 0  # Air for all other blocks
    
    mc.getBlock.side_effect = get_block_side_effect
    
    requirements = {material_name: 1}
    # Run mining starting at position (0, 5, 0)
    result = await strategy.mine(requirements, (0, 5, 0), {}, {})
    
    # Verify that diamond ore was found and collected
    assert material_name in result
    assert result[material_name] >= 1
    mc.setBlock.assert_called()  # Verify blocks were mined
    ws.log_event.assert_any_call("BLOCK_MINED", "test_agent", ANY)

@pytest.mark.asyncio
async def test_mine_vein_bfs_respects_max_size(mock_dependencies):
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    strategy.max_vein_size = 3
    
    target_id = 56
    mat_name = "DIAMOND_ORE"
    strategy.block_names[target_id] = mat_name
    
    # Always return the block type to simulate an infinite vein
    mc.getBlock.return_value = target_id
    
    # Initialize queue and run Breadth First Search (BFS)
    strategy.vein_queue = [(0, 10, 0, target_id, mat_name)]
    await strategy.mine_vein_bfs({mat_name: 10})
    
    # Should stop at max vein size
    assert strategy.collected_materials[mat_name] == 3
    assert len(strategy.vein_queue) > 0 # Still has items in queue

@pytest.mark.asyncio
async def test_lock_region_failure(mock_dependencies):
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    
    # Simulate region already locked
    strategy.locked_regions.add((10, 20))
    
    result = await strategy.mine({"COAL": 1}, (10, 5, 20), {}, {})
    
    assert result == {}
    ws.log_event.assert_any_call("REGION_LOCK_FAILED", "test_agent", ANY)

@pytest.mark.asyncio
async def test_requirements_met_stops_mining(mock_dependencies):
    """Test that mining stops when requirements are met during mining"""
    mc, ws, agent = mock_dependencies
    strategy = VeinSearchStrategy(mc, "test_agent", ws, agent)
    
    mat = "IRON_ORE"
    target_block_id = 15  # IRON_ORE block ID
    strategy.block_names[target_block_id] = mat
    
    # Mock getHeight to return a surface level
    mc.getHeight.return_value = 10
    
    # Return iron ore at the first block checked and air elsewhere
    def get_block_side_effect(x, y, z):
        # Return iron ore at the starting position
        if x == 0 and y == 10 and z == 0:
            return target_block_id
        return 0  # Air for all others
    
    mc.getBlock.side_effect = get_block_side_effect
    
    # Set requirement for only 1 iron ore
    requirements = {mat: 1}
    
    # Mine should collect 1 iron ore and stop
    result = await strategy.mine(requirements, (0, 5, 0), {}, {})
    
    # Verify that iron ore was collected
    assert mat in result
    assert result[mat] >= 1
    # Verify mining completed (not interrupted)
    ws.log_event.assert_any_call("MINING_COMPLETED", "test_agent", ANY)