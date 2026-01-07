import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.ExplorerBot import ExplorerBot
import mcpi.block as block

@pytest.fixture
def mock_mc():
    return MagicMock()

@pytest.fixture
def mock_workspace():
    mw = MagicMock()
    mw.post_message = MagicMock()
    return mw

@pytest.fixture
def bot(mock_mc, mock_workspace):
    # Mocking BaseAgent which is the parent of ExplorerBot
    with patch('agents.ExplorerBot.BaseAgent', autospec=True):
        bot_instance = ExplorerBot(mock_mc, mock_workspace)
        # Mocking the state enum behavior
        bot_instance.state = MagicMock()
        bot_instance.state.value = "IDLE"
        bot_instance.pda_task = None
        bot_instance.args = {}
        return bot_instance

def test_init(bot):
    assert bot.show_regions is False
    assert bot.display_duration == 15.0
    assert bot.request_queue == []
    assert bot.waiting_confirmation is False

def test_generate_elevation_map(bot):
    heights = {(0, 0): 10, (1, 0): 10, (0, 1): 11}
    elevation_map = bot.generate_elevation_map(heights)
    assert 10 in elevation_map
    assert 11 in elevation_map
    assert (0, 0) in elevation_map[10]
    assert (1, 0) in elevation_map[10]
    assert (0, 1) in elevation_map[11]

def test_find_largest_rectangle(bot):
    grid = [
        [1, 1, 0],
        [1, 1, 1],
        [1, 1, 1]
    ]

    rect = bot.find_largest_rectangle(grid, 3, 3)

    assert rect is not None
    x, y, w, h = rect
    assert w * h == 6

def test_is_region_stable(bot):
    bot.UNSTABLE_IDS = {block.WATER.id}
    region = {'y': 10, 'blocks': [(0, 0), (1, 0)]}
    
    # Stable region case
    bot.blocks = {
        (0, 10, 0): MagicMock(id=block.GRASS.id),
        (1, 10, 0): MagicMock(id=block.GRASS.id)
    }
    assert bot.is_region_stable(region) is True
    
    # Unstable region case
    bot.blocks[(1, 10, 0)].id = block.WATER.id
    assert bot.is_region_stable(region) is False

def test_handle_command_toggle(bot, mock_mc):
    command = {
        "payload": {
            "action": "toggle",
            "parameters": {"display": 20.0}
        }
    }
    result = bot.handle_command(command)
    assert result is True
    assert bot.show_regions is True
    assert bot.display_duration == 20.0
    mock_mc.postToChat.assert_called()

@pytest.mark.asyncio
async def test_perceive(bot):
    bot.scan_world = MagicMock(return_value=({(0, 0): 10}, {(0, 10, 0): MagicMock()}))
    
    with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = ({(0, 0): 10}, {(0, 10, 0): MagicMock()})
        heights = await bot.perceive(x=0, z=0, range=1)
        
    assert bot.has_new_scan is True
    assert (0, 0) in heights
    assert heights[(0, 0)] == 10

@pytest.mark.asyncio
async def test_decide_no_scan(bot):
    bot.has_new_scan = False
    result = await bot.decide()
    assert result is None

@pytest.mark.asyncio
async def test_decide_success(bot):
    bot.has_new_scan = True
    bot.heights = {(10, 10): 5}
    bot.x0, bot.z0, bot.area = 10, 10, 1
    bot.blocks = {(10, 5, 10): MagicMock(id=block.GRASS.id)}
    
    with patch.object(bot, 'identify_flat_regions', return_value=[{'y': 5, 'blocks': [(10, 10)], 'width': 1, 'depth': 1}]):
        result = await bot.decide()
        assert len(result) == 1
        assert result[0]['y'] == 5

def test_handle_command_queue(bot, mock_mc):
    bot.args = {"active": True}
    bot.waiting_confirmation = True
    bot.pending_command = {"payload": {"action": "start"}}
    
    command = {"payload": {"action": "queue"}}
    result = bot.handle_command(command)
    
    assert result is True
    assert len(bot.request_queue) == 1
    assert bot.waiting_confirmation is False
    assert bot.pending_command is None


def test_handle_command_confirm(bot, mock_mc):
    """Test that confirm command processes pending exploration request"""
    bot.args = {"active": True}
    bot.waiting_confirmation = True
    bot.pending_command = {"payload": {"action": "start", "parameters": {"x": 10, "z": 20}}}
    
    command = {"payload": {"action": "confirm"}}
    result = bot.handle_command(command)
    
    assert result is True
    assert bot.waiting_confirmation is False
    assert bot.pending_command is None
    mock_mc.postToChat.assert_called()


def test_handle_command_set(bot, mock_mc):
    """Test that set command updates arguments and triggers exploration"""
    bot.args = {}
    
    command = {"payload": {"action": "set", "parameters": {"x": 100, "z": 200, "range": 50}}}
    result = bot.handle_command(command)
    
    assert result is True
    assert bot.args.get("x") == 100
    assert bot.args.get("z") == 200
    assert bot.args.get("range") == 50


def test_clear_visualization(bot, mock_mc):
    """Test that clear_visualization handles empty displayed regions"""
    bot.displayed_regions = []
    bot.clear_visualization()  # Should not raise an error
    assert bot.displayed_regions == []