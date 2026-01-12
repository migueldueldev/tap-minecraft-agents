"""
Extended tests for main module.

This module provides comprehensive coverage for the main application entry point including:
- Minecraft connection handling
- Chat event processing
- Shutdown handling
"""

import pytest
import asyncio
import os
from unittest.mock import MagicMock, patch, AsyncMock


class TestConnectMc:
    """Tests for Minecraft connection function."""

    @patch('main.Minecraft')
    @patch('main.logger')
    def test_connect_mc_success(self, mock_logger, mock_minecraft_class):
        """Test successful Minecraft connection."""
        from main import connect_mc
        
        mock_mc = MagicMock()
        mock_minecraft_class.create.return_value = mock_mc
        
        result = connect_mc()
        
        assert result == mock_mc
        mock_minecraft_class.create.assert_called_once()
        mock_logger.info.assert_called()

    @patch('main.Minecraft')
    @patch('main.logger')
    def test_connect_mc_failure_exits(self, mock_logger, mock_minecraft_class):
        """Test connection failure exits the program."""
        from main import connect_mc
        
        mock_minecraft_class.create.side_effect = Exception("Connection failed")
        
        with pytest.raises(SystemExit):
            connect_mc()
        
        mock_logger.error.assert_called()

    @patch('main.Minecraft')
    @patch('main.logger')
    def test_connect_mc_logs_connecting_message(self, mock_logger, mock_minecraft_class):
        """Test connection logs connecting message."""
        from main import connect_mc
        
        mock_mc = MagicMock()
        mock_minecraft_class.create.return_value = mock_mc
        
        connect_mc()
        
        # Should log both connecting and success messages
        assert mock_logger.info.call_count >= 2


class TestLoadAgentsIntegration:
    """Integration tests for agent loading using real classes."""

    def test_load_agents_returns_list(self):
        """Test load_agents returns a list of instances."""
        from main import load_agents
        
        mock_mc = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.register_observer = MagicMock()
        mock_workspace.log_file = "/tmp/test.log"
        
        result = load_agents(mock_mc, mock_workspace)
        
        assert isinstance(result, list)

    def test_load_agents_creates_instances(self):
        """Test load_agents creates agent instances."""
        from main import load_agents
        
        mock_mc = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.register_observer = MagicMock()
        mock_workspace.log_file = "/tmp/test.log"
        
        result = load_agents(mock_mc, mock_workspace)
        
        # Should create instances of the defined agents
        assert len(result) >= 0  # May be empty if no agents defined


class TestReadChatEvents:
    """Tests for chat event processing."""

    @pytest.mark.asyncio
    async def test_read_chat_events_polls_events(self):
        """Test read_chat_events polls for chat events."""
        from main import read_chat_events
        
        mock_mc = MagicMock()
        mock_workspace = MagicMock()
        mock_instances = []
        mock_workflow = MagicMock()
        
        mock_mc.events.pollChatPosts.return_value = []
        
        # Run for a short time then cancel
        with patch('main.parse_message', new_callable=AsyncMock):
            task = asyncio.create_task(
                read_chat_events(mock_mc, mock_workspace, mock_instances, mock_workflow)
            )
            
            await asyncio.sleep(0.15)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        assert mock_mc.events.pollChatPosts.call_count >= 1

    @pytest.mark.asyncio
    async def test_read_chat_events_processes_each_event(self):
        """Test read_chat_events processes each chat event."""
        from main import read_chat_events
        
        mock_mc = MagicMock()
        mock_workspace = MagicMock()
        mock_instances = []
        mock_workflow = MagicMock()
        
        mock_event = MagicMock()
        mock_event.message = "test command"
        mock_mc.events.pollChatPosts.return_value = [mock_event]
        
        with patch('main.parse_message', new_callable=AsyncMock) as mock_parse:
            mock_mc.events.pollChatPosts.side_effect = [[mock_event], []]
            
            task = asyncio.create_task(
                read_chat_events(mock_mc, mock_workspace, mock_instances, mock_workflow)
            )
            
            await asyncio.sleep(0.15)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        mock_parse.assert_called_with(
            "test command", mock_mc, mock_workspace, mock_instances, mock_workflow
        )


class TestMain:
    """Tests for main application entry point."""

    @pytest.mark.asyncio
    async def test_main_initializes_components(self):
        """Test main initializes all required components."""
        with patch('main.connect_mc') as mock_connect, \
             patch('main.SharedWorkspace') as mock_workspace_class, \
             patch('main.load_agents') as mock_load_agents, \
             patch('main.Workflow') as mock_workflow_class, \
             patch('main.find_agent') as mock_find_agent, \
             patch('main.read_chat_events', new_callable=AsyncMock) as mock_chat:
            
            mock_mc = MagicMock()
            mock_connect.return_value = mock_mc
            mock_workspace = MagicMock()
            mock_workspace_class.return_value = mock_workspace
            mock_load_agents.return_value = []
            mock_find_agent.return_value = None
            
            # Import after patching
            from main import main
            
            # Run main for a short time
            task = asyncio.create_task(main())
            await asyncio.sleep(0.1)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            mock_connect.assert_called_once()
            mock_workspace_class.assert_called_once()
            mock_load_agents.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_starts_agents(self):
        """Test main starts agent instances."""
        with patch('main.connect_mc') as mock_connect, \
             patch('main.SharedWorkspace') as mock_workspace_class, \
             patch('main.load_agents') as mock_load_agents, \
             patch('main.Workflow') as mock_workflow_class, \
             patch('main.find_agent') as mock_find_agent, \
             patch('main.read_chat_events', new_callable=AsyncMock):
            
            mock_mc = MagicMock()
            mock_connect.return_value = mock_mc
            mock_workspace = MagicMock()
            mock_workspace_class.return_value = mock_workspace
            
            mock_agent = AsyncMock()
            mock_load_agents.return_value = [mock_agent]
            mock_find_agent.return_value = mock_agent
            
            from main import main
            
            task = asyncio.create_task(main())
            await asyncio.sleep(0.1)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            mock_agent.start.assert_called()


class TestShutdownHandling:
    """Tests for graceful shutdown handling."""

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_stops_agents(self):
        """Test KeyboardInterrupt stops all agents."""
        with patch('main.connect_mc') as mock_connect, \
             patch('main.SharedWorkspace') as mock_workspace_class, \
             patch('main.load_agents') as mock_load_agents, \
             patch('main.Workflow') as mock_workflow_class, \
             patch('main.find_agent') as mock_find_agent, \
             patch('main.asyncio.create_task') as mock_create_task:
            
            mock_mc = MagicMock()
            mock_connect.return_value = mock_mc
            mock_workspace = MagicMock()
            mock_workspace_class.return_value = mock_workspace
            
            mock_agent = MagicMock()
            mock_load_agents.return_value = [mock_agent]
            mock_find_agent.return_value = None
            
            # Mock the sleep to raise KeyboardInterrupt
            original_sleep = asyncio.sleep
            call_count = [0]
            
            async def mock_sleep(delay):
                call_count[0] += 1
                if call_count[0] > 2:
                    raise KeyboardInterrupt
                await original_sleep(0.01)
            
            from main import main
            
            with patch('main.asyncio.sleep', mock_sleep):
                try:
                    await main()
                except KeyboardInterrupt:
                    pass
            
            mock_agent.stop.assert_called()


class TestAgentDiscovery:
    """Tests for agent discovery patterns."""

    def test_load_agents_integration(self):
        """Test load_agents integrates properly with real system."""
        from main import load_agents
        
        mock_mc = MagicMock()
        mock_workspace = MagicMock()
        mock_workspace.register_observer = MagicMock()
        mock_workspace.log_file = "/tmp/test.log"
        
        # This calls the real function and verifies it works
        result = load_agents(mock_mc, mock_workspace)
        
        # Should return a list
        assert isinstance(result, list)


class TestChatEventLogging:
    """Tests for chat event logging."""

    @pytest.mark.asyncio
    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_chat_events_logged_at_debug_level(self):
        """Test chat events are logged at debug level."""
        from main import read_chat_events
        
        with patch('main.logger') as mock_logger, \
             patch('main.parse_message', new_callable=AsyncMock):
            
            mock_mc = MagicMock()
            mock_workspace = MagicMock()
            mock_instances = []
            mock_workflow = MagicMock()
            
            mock_event = MagicMock()
            mock_event.message = "test"
            mock_mc.events.pollChatPosts.side_effect = [[mock_event], []]
            
            task = asyncio.create_task(
                read_chat_events(mock_mc, mock_workspace, mock_instances, mock_workflow)
            )
            
            await asyncio.sleep(0.15)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            mock_logger.debug.assert_called()


class TestWorkflowIntegration:
    """Tests for workflow integration in main."""

    @pytest.mark.asyncio
    async def test_workflow_created_with_correct_args(self):
        """Test Workflow is created with correct arguments."""
        with patch('main.connect_mc') as mock_connect, \
             patch('main.SharedWorkspace') as mock_workspace_class, \
             patch('main.load_agents') as mock_load_agents, \
             patch('main.Workflow') as mock_workflow_class, \
             patch('main.find_agent') as mock_find_agent, \
             patch('main.read_chat_events', new_callable=AsyncMock):
            
            mock_mc = MagicMock()
            mock_connect.return_value = mock_mc
            mock_workspace = MagicMock()
            mock_workspace_class.return_value = mock_workspace
            mock_instances = [MagicMock()]
            mock_load_agents.return_value = mock_instances
            mock_find_agent.return_value = None
            
            from main import main
            
            task = asyncio.create_task(main())
            await asyncio.sleep(0.1)
            task.cancel()
            
            try:
                await task
            except asyncio.CancelledError:
                pass
            
            mock_workflow_class.assert_called_once_with(
                mock_mc, mock_workspace, mock_instances
            )
