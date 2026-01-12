import pytest
from unittest.mock import MagicMock, patch
from agents.MinerBot import MinerBot
from BaseAgent import AgentState

class MockPos:
    def __init__(self, x=0, y=0, z=0):
        self.x = x
        self.y = y
        self.z = z

@pytest.fixture
def mock_mc():
    mc = MagicMock()
    mc.player.getTilePos.return_value = MockPos(10, 20, 30)
    return mc

@pytest.fixture
def mock_workspace():
    workspace = MagicMock()
    workspace.log_event = MagicMock()
    workspace.post_message = MagicMock()
    return workspace

@pytest.fixture
def miner_bot(mock_mc, mock_workspace):
    # Mock the load strategies method to return mock strategies
    with patch.object(MinerBot, 'load_strategies', return_value={
        'vertical': MagicMock(),
        'grid': MagicMock(),
        'vein': MagicMock()
    }):
        bot = MinerBot(mock_mc, mock_workspace)
        return bot

def test_initialization(miner_bot):
    assert miner_bot.inventory == {}
    assert miner_bot.mining_strategy_name == ""
    assert "vertical" in miner_bot.strategy_map

def test_handle_material_requirements_auto_provide(miner_bot):
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
    
    # Cobblestone is in auto provided materials
    assert miner_bot.inventory["COBBLESTONE"] == 10
    assert "IRON_ORE" not in miner_bot.inventory or miner_bot.inventory["IRON_ORE"] == 0
    assert miner_bot.material_requirements["IRON_ORE"] == 5

def test_get_minable_requirements_conversion(miner_bot):
    # Requirement: 1 IRON_BLOCK (needs 9 IRON_ORE)
    miner_bot.material_requirements = {"IRON_BLOCK": 1}
    miner_bot.inventory = {}
    
    reqs = miner_bot.get_minable_requirements()
    assert reqs["IRON_ORE"] == 9

def test_convert_ores_to_blocks(miner_bot):
    miner_bot.material_requirements = {"IRON_BLOCK": 2}
    # 20 ores = 2 blocks with 2 ores left over
    miner_bot.inventory = {"IRON_ORE": 20}
    
    miner_bot.convert_ores_to_blocks()
    
    assert miner_bot.inventory["IRON_BLOCK"] == 2
    assert miner_bot.inventory["IRON_ORE"] == 2

def test_requirements_fulfilled(miner_bot):
    miner_bot.material_requirements = {"STONE": 5}
    miner_bot.inventory = {"STONE": 2}
    assert miner_bot.requirements_fulfilled() is False
    
    miner_bot.inventory = {"STONE": 5}
    assert miner_bot.requirements_fulfilled() is True

def test_handle_command_set_strategy(miner_bot):
    command = {
        "payload": {
            "action": "set",
            "parameters": {"strategy": "grid"}
        }
    }
    miner_bot.handle_command(command)
    assert miner_bot.mining_strategy_name == "grid"
    assert miner_bot.mining_strategy is None

def test_handle_command_fulfill(miner_bot):
    command = {
        "payload": {
            "action": "fulfill"
        }
    }
    miner_bot.ready_to_mine = False
    miner_bot.handle_command(command)
    assert miner_bot.ready_to_mine is True

def test_set_state_releases_locks_on_error(miner_bot, mock_workspace):
    """Test that MinerBot releases locks when transitioning to ERROR state"""
    # Set an initial state first
    miner_bot.state = AgentState.RUNNING
    
    # Create a mock mining strategy
    mock_strategy = MagicMock()
    miner_bot.mining_strategy = mock_strategy
    
    assert hasattr(miner_bot, 'set_state')
    
    # Change to ERROR state to trigger lock release
    miner_bot.set_state(AgentState.ERROR, reason="Test Error")
    
    # Verify the state was actually changed
    assert miner_bot.state == AgentState.ERROR
    
    # Verify that locks were released
    mock_strategy.release_all_locks.assert_called_once()


def test_set_state_no_locks_released_on_running(miner_bot, mock_workspace):
    """Test that MinerBot does NOT release locks when transitioning to RUNNING"""
    miner_bot.state = AgentState.IDLE
    
    # Create a mock mining strategy
    mock_strategy = MagicMock()
    miner_bot.mining_strategy = mock_strategy
    
    miner_bot.set_state(AgentState.RUNNING, reason="Starting")
    
    # Verify that locks were not released
    mock_strategy.release_all_locks.assert_not_called()

@pytest.mark.asyncio
async def test_perceive_updates_coords(miner_bot, mock_mc):
    mock_mc.player.getTilePos.return_value = MockPos(1, 2, 3)
    mock_mc.getHeight.return_value = 64  # Surface height above default mining depth
    coords = await miner_bot.perceive()
    assert coords["x"] == 1
    assert coords["y"] == 5  # Default mining depth
    assert coords["z"] == 3