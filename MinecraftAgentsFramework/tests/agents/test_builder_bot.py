import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from agents.builder_bot import BuilderBot
from base_agent import AgentState

@pytest.fixture
def mock_mc():
    return MagicMock()

@pytest.fixture
def mock_workspace():
    workspace = MagicMock()
    workspace.get_messages.return_value = []
    return workspace

@pytest.fixture
def builder(mock_mc, mock_workspace):
    return BuilderBot(mock_mc, mock_workspace)

def test_initialization(builder):
    assert builder.current_plan is None
    assert builder.inventory == {}
    assert builder.is_building is False
    assert builder.build_ready is False

def test_pending_materials(builder):
    builder.bom = {"STONE": 10, "DIRT": 5, "DIAMOND_ORE": 2}
    builder.inventory = {"STONE": 4}
    # DIRT should be auto provided, STONE is missing 6, DIAMOND_ORE is missing 2
    pending = builder._pending_materials()
    assert pending == {"STONE": 6, "DIAMOND_ORE": 2}
    assert "DIRT" not in pending

def test_compute_bom(builder):
    builder.structured_blocks = {
        0: [{"block": "STONE", "x": 0, "z": 0}, {"block": "STONE", "x": 1, "z": 0}],
        1: [{"block": "GLASS", "x": 0, "z": 0}]
    }
    bom = builder._compute_bom()
    assert bom == {"STONE": 2, "GLASS": 1}

def test_find_build_position(builder):
    builder.structured_blocks = {0: [{"x": 1, "z": 1, "block": "STONE"}]} # Size 2x2
    builder.terrain_data = {
        "regions": [
            {"width": 5, "depth": 5, "y": 64, "blocks": [{"x": 10, "z": 10}]},
            {"width": 1, "depth": 1, "y": 64, "blocks": [{"x": 0, "z": 0}]}
        ]
    }
    pos = builder._find_build_position()
    assert pos == (10, 64, 10) # Should pick the 5x5 region as 2x2 fits there but not in 1x1

@pytest.mark.asyncio
async def test_perceive_inventory(builder, mock_workspace):
    msg = {
        "type": "inventory.v1",
        "payload": {
            "materials": [{"material": "IRON_ORE", "collected": 5}],
            "complete": True
        }
    }
    builder.get_messages = MagicMock(return_value=[msg])
    await builder.perceive()
    assert builder.inventory["IRON_ORE"] == 5

@pytest.mark.asyncio
async def test_decide_waiting_state(builder):
    builder.current_plan = "test_house"
    builder.bom = {"DIAMOND_BLOCK": 10}
    builder.inventory = {}
    builder.set_state = MagicMock()
    
    await builder.decide()
    builder.set_state.assert_called_with(AgentState.WAITING, "Waiting materials for building")

@pytest.mark.asyncio
async def test_execute_build_process_success(builder, mock_mc):
    builder.build_position = (0, 0, 0)
    builder.structured_blocks = {
        0: [{"x": 1, "z": 1, "block": "STONE", "data": 0}]
    }
    builder.is_building = False
    
    # Mock id of STONE block
    with patch("mcpi.block.STONE.id", 1):
        await builder._execute_build_process()
    
    mock_mc.setBlock.assert_called_with(1, 0, 1, 1, 0)
    assert builder.is_building is False

def test_handle_command_bom_no_plan(builder, mock_mc):
    builder.bom = {}
    builder.handle_command({"payload": {"action": "bom", "parameters": {}}})
    mock_mc.postToChat.assert_called_with("Builder agent has no plan set. Set a plan to view the Bill of Materials.")

def test_handle_command_plan_list(builder, mock_mc):
    with patch.object(BuilderBot, "_discover_plans", return_value=["castle", "tower"]):
        builder.handle_command({"payload": {"action": "plan", "parameters": {"list": True}}})
        mock_mc.postToChat.assert_any_call("castle")
        mock_mc.postToChat.assert_any_call("tower")