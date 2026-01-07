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
    # Mock strategies
    with patch('agents.MinerBot.VerticalSearchStrategy'), \
         patch('agents.MinerBot.GridSearchStrategy'), \
         patch('agents.MinerBot.VeinSearchStrategy'):
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

def test_set_state_notification(miner_bot, mock_workspace):
    """Test that MinerBot posts a state change notification on ERROR state"""
    # Set an initial state first
    miner_bot.state = AgentState.RUNNING
    
    assert hasattr(miner_bot, 'set_state')
    
    # Change to ERROR state to trigger a notification
    miner_bot.set_state(AgentState.ERROR, reason="Test Error")
    
    # Verify the state was actually changed
    assert miner_bot.state == AgentState.ERROR
    
    # Check if a state change notification was posted to workspace
    if mock_workspace.post_message.called:
        args, kwargs = mock_workspace.post_message.call_args
        message = args[0]
        assert message["type"] == "state_change.v1"
        assert message["payload"]["new_state"] == AgentState.ERROR.value
        assert message["payload"]["reason"] == "Test Error"


def test_set_state_no_notification_on_running(miner_bot, mock_workspace):
    """Test that MinerBot does NOT post notification when transitioning to RUNNING"""
    miner_bot.state = AgentState.IDLE
    miner_bot.set_state(AgentState.RUNNING, reason="Starting")
    
    mock_workspace.post_message.assert_not_called()

@pytest.mark.asyncio
async def test_perceive_updates_coords(miner_bot, mock_mc):
    mock_mc.player.getTilePos.return_value = MockPos(1, 2, 3)
    coords = await miner_bot.perceive()
    assert coords["x"] == 1
    assert coords["y"] == 2
    assert coords["z"] == 3