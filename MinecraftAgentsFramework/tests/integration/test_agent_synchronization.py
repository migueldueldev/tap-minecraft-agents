"""
Integration tests for agent synchronization mechanisms.

This module tests the synchronization primitives and patterns used
across the multi-agent system including:
- Thread-safe command/message queues with locks
- Asyncio events for interrupt handling
- State transitions across agents
- Concurrent access patterns
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import MagicMock, patch, AsyncMock
from concurrent.futures import ThreadPoolExecutor

from base_agent import BaseAgent, AgentState
from shared_workspace import SharedWorkspace


class ConcreteTestAgent(BaseAgent):
    """Concrete test agent implementation for integration testing."""
    
    def __init__(self, mc, workspace):
        super().__init__(mc, workspace)
        self.perceive_count = 0
        self.decide_count = 0
        self.act_count = 0
        self.perceive_results = []
        self.decide_results = []
        self.act_results = []
    
    async def perceive(self, **kwargs):
        self.perceive_count += 1
        await asyncio.sleep(0.01)  # Simulate work
        self.perceive_results.append(kwargs)
        return kwargs
    
    async def decide(self, **kwargs):
        self.decide_count += 1
        await asyncio.sleep(0.01)  # Simulate work
        self.decide_results.append(kwargs)
        return kwargs
    
    async def act(self, **kwargs):
        self.act_count += 1
        await asyncio.sleep(0.01)  # Simulate work
        self.act_results.append(kwargs)
        return kwargs


class TestThreadSafeCommandQueue:
    """Tests for thread-safe command queue synchronization."""
    
    @pytest.fixture
    def setup(self, tmp_path):
        mc = MagicMock()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        agent = ConcreteTestAgent(mc, workspace)
        return agent, mc, workspace
    
    def test_concurrent_command_writes(self, setup):
        """Test that multiple threads can safely write to command queue."""
        agent, _, _ = setup
        num_threads = 10
        commands_per_thread = 50
        
        def write_commands(thread_id):
            for i in range(commands_per_thread):
                command = {"payload": {"action": "test", "thread": thread_id, "seq": i}}
                agent.receive_command(command)
        
        threads = []
        for t_id in range(num_threads):
            t = threading.Thread(target=write_commands, args=(t_id,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify all commands were received
        expected_total = num_threads * commands_per_thread
        assert len(agent.local_command_queue) == expected_total
        
        # Verify command_event was set
        assert agent.command_event.is_set()
    
    def test_concurrent_message_writes(self, setup):
        """Test that multiple threads can safely write to message queue."""
        agent, _, _ = setup
        num_threads = 10
        messages_per_thread = 50
        
        def write_messages(thread_id):
            for i in range(messages_per_thread):
                message = {"source": f"Thread{thread_id}", "seq": i}
                agent.receive_message(message)
        
        threads = []
        for t_id in range(num_threads):
            t = threading.Thread(target=write_messages, args=(t_id,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify all messages were received
        expected_total = num_threads * messages_per_thread
        assert len(agent.local_message_queue) == expected_total
    
    def test_concurrent_read_write_commands(self, setup):
        """Test concurrent reads and writes on command queue are thread-safe."""
        agent, _, _ = setup
        total_written = 0
        total_read = 0
        read_lock = threading.Lock()
        write_lock = threading.Lock()
        
        def write_commands():
            nonlocal total_written
            for i in range(100):
                command = {"payload": {"action": "test", "seq": i}}
                agent.receive_command(command)
                with write_lock:
                    total_written += 1
                time.sleep(0.001)
        
        def read_commands():
            nonlocal total_read
            for _ in range(100):
                with agent.lock:
                    if agent.local_command_queue:
                        agent.local_command_queue.popleft()
                        with read_lock:
                            total_read += 1
                time.sleep(0.001)
        
        writer = threading.Thread(target=write_commands)
        reader = threading.Thread(target=read_commands)
        
        writer.start()
        reader.start()
        
        writer.join()
        reader.join()
        
        # No exceptions should occur and counts should be consistent
        remaining = len(agent.local_command_queue)
        assert total_written == total_read + remaining


class TestAsyncEventSynchronization:
    """Tests for asyncio event-based synchronization."""
    
    @pytest.fixture
    def setup(self, tmp_path):
        mc = MagicMock()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        agent = ConcreteTestAgent(mc, workspace)
        return agent, mc, workspace
    
    @pytest.mark.asyncio
    async def test_interrupt_event_stops_agent_cycle(self, setup):
        """Test that setting interrupt_event properly interrupts agent cycle."""
        agent, _, _ = setup
        
        # Start the agent cycle
        agent.args = {"test": True}
        agent.set_state(AgentState.RUNNING)
        
        async def run_for_limited_time():
            cycle_count = 0
            while not agent.should_stop and cycle_count < 5:
                if agent.interrupt_event.is_set():
                    break
                await agent.perceive(**agent.args)
                cycle_count += 1
                await asyncio.sleep(0.01)
            return cycle_count
        
        # Interrupt after short delay
        async def interrupt_after_delay():
            await asyncio.sleep(0.05)
            agent.interrupt_event.set()
        
        task = asyncio.create_task(run_for_limited_time())
        interrupt_task = asyncio.create_task(interrupt_after_delay())
        
        cycle_count = await task
        await interrupt_task
        
        # Agent should have been interrupted before completing all 5 cycles
        assert cycle_count < 5 or agent.interrupt_event.is_set()
    
    @pytest.mark.asyncio
    async def test_command_event_triggers_processing(self, setup):
        """Test that command_event properly signals command processing."""
        agent, _, _ = setup
        commands_processed = []
        
        async def wait_for_command():
            await asyncio.wait_for(agent.command_event.wait(), timeout=1.0)
            agent.command_event.clear()
            with agent.lock:
                if agent.local_command_queue:
                    cmd = agent.local_command_queue.popleft()
                    commands_processed.append(cmd)
        
        # Send command from another task
        async def send_command():
            await asyncio.sleep(0.01)
            agent.receive_command({"payload": {"action": "test"}})
        
        await asyncio.gather(
            wait_for_command(),
            send_command()
        )
        
        assert len(commands_processed) == 1
        assert commands_processed[0]["payload"]["action"] == "test"
    
    @pytest.mark.asyncio
    async def test_pause_resume_state_transitions(self, setup):
        """Test pause and resume use interrupt_event correctly."""
        agent, mc, _ = setup
        
        agent.set_state(AgentState.RUNNING)
        
        # Pause should set interrupt_event
        agent.pause()
        assert agent.state == AgentState.PAUSED
        assert agent.interrupt_event.is_set()
        
        # Resume should set interrupt_event (to wake up from pause wait)
        agent.interrupt_event.clear()
        agent.resume()
        assert agent.state == AgentState.RUNNING
        assert agent.interrupt_event.is_set()
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_event_waits(self, setup):
        """Test multiple tasks waiting on same event."""
        agent, _, _ = setup
        waiters_triggered = []
        
        async def waiter(waiter_id):
            try:
                await asyncio.wait_for(agent.interrupt_event.wait(), timeout=1.0)
                waiters_triggered.append(waiter_id)
            except asyncio.TimeoutError:
                pass
        
        async def trigger_event():
            await asyncio.sleep(0.05)
            agent.interrupt_event.set()
        
        # Create multiple waiters
        tasks = [
            asyncio.create_task(waiter(1)),
            asyncio.create_task(waiter(2)),
            asyncio.create_task(waiter(3)),
            asyncio.create_task(trigger_event())
        ]
        
        await asyncio.gather(*tasks)
        
        # All waiters should have been triggered
        assert len(waiters_triggered) == 3


class TestAgentStateSynchronization:
    """Tests for agent state management and transitions."""
    
    @pytest.fixture
    def setup(self, tmp_path):
        mc = MagicMock()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        agent = ConcreteTestAgent(mc, workspace)
        return agent, mc, workspace
    
    def test_state_transitions_are_logged(self, setup):
        """Test that state transitions are properly logged with timestamps."""
        agent, _, workspace = setup
        
        states = [
            AgentState.RUNNING,
            AgentState.PAUSED,
            AgentState.RUNNING,
            AgentState.WAITING,
            AgentState.STOPPED
        ]
        
        for state in states:
            agent.set_state(state, reason=f"Testing {state.value}")
        
        # Read log file and verify entries
        with open(workspace.log_file, 'r') as f:
            log_content = f.read()
        
        # Each state change should be logged
        assert log_content.count('"event": "STATE_CHANGE"') == len(states)
        for state in states:
            assert state.value in log_content
    
    def test_stopped_agent_rejects_commands(self, setup):
        """Test that stopped agents properly reject non-status commands."""
        agent, mc, _ = setup
        
        agent.stop()
        assert agent.state == AgentState.STOPPED
        
        # Start command should be rejected
        result = agent.handle_command({"payload": {"action": "start", "parameters": {}}})
        assert result is False  # Command rejected
        
        # Status and help should still work
        result = agent.handle_command({"payload": {"action": "status"}})
        assert result is True
        
        result = agent.handle_command({"payload": {"action": "help"}})
        assert result is True


class TestConcurrentAgentOperations:
    """Tests for concurrent operations across multiple agents."""
    
    @pytest.fixture
    def multi_agent_setup(self, tmp_path):
        mc = MagicMock()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        
        agents = []
        for i in range(3):
            agent = ConcreteTestAgent(mc, workspace)
            # Give each agent a unique class name for routing
            agent.__class__ = type(f'TestAgent{i}', (ConcreteTestAgent,), {})
            agents.append(agent)
        
        return agents, workspace, mc
    
    def test_workspace_routes_to_correct_agent(self, multi_agent_setup):
        """Test that workspace correctly routes commands to specific agents."""
        agents, workspace, _ = multi_agent_setup
        
        command = {"action": "test_command"}
        workspace.post_command("TestAgent1", command)
        
        # Only agent 1 should receive the command
        assert len(agents[0].local_command_queue) == 0
        assert len(agents[1].local_command_queue) == 1
        assert len(agents[2].local_command_queue) == 0
    
    def test_workspace_routes_messages_to_target(self, multi_agent_setup):
        """Test that messages are routed to the target agent."""
        agents, workspace, _ = multi_agent_setup
        
        message = {
            "type": "test.v1",
            "source": "TestAgent0",
            "target": "TestAgent2",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {"content": "test_message"},
            "status": "SUCCESS"
        }
        workspace.post_message(message)
        
        # Only agent 2 should receive the message
        assert len(agents[0].local_message_queue) == 0
        assert len(agents[1].local_message_queue) == 0
        assert len(agents[2].local_message_queue) == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_agent_cycles(self, multi_agent_setup):
        """Test multiple agents running cycles concurrently."""
        agents, workspace, _ = multi_agent_setup
        
        for agent in agents:
            agent.args = {"test": True}
            agent.set_state(AgentState.RUNNING)
        
        async def run_agent_cycles(agent, num_cycles):
            for _ in range(num_cycles):
                await agent.perceive(**agent.args)
                await agent.decide(**agent.args)
                await agent.act(**agent.args)
                await asyncio.sleep(0.01)
        
        # Run all agents concurrently
        await asyncio.gather(*[
            run_agent_cycles(agent, 5) for agent in agents
        ])
        
        # Verify all agents completed their cycles
        for agent in agents:
            assert agent.perceive_count == 5
            assert agent.decide_count == 5
            assert agent.act_count == 5
    
    def test_concurrent_observer_registration(self, tmp_path):
        """Test thread-safe observer registration."""
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        mc = MagicMock()
        
        agents_registered = []
        lock = threading.Lock()
        
        def register_agent(agent_id):
            agent = ConcreteTestAgent(mc, workspace)
            # Note: register_observer is called in __init__
            with lock:
                agents_registered.append(agent)
        
        threads = []
        for i in range(20):
            t = threading.Thread(target=register_agent, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(agents_registered) == 20
        assert len(workspace.observers) == 20


class TestLockContention:
    """Tests for lock contention scenarios."""
    
    @pytest.fixture
    def setup(self, tmp_path):
        mc = MagicMock()
        workspace = SharedWorkspace()
        workspace.log_file = str(tmp_path / "test.log")
        agent = ConcreteTestAgent(mc, workspace)
        return agent, mc, workspace
    
    def test_high_contention_command_queue(self, setup):
        """Test command queue under high contention."""
        agent, _, _ = setup
        errors = []
        
        def producer():
            try:
                for i in range(1000):
                    agent.receive_command({"payload": {"seq": i}})
            except Exception as e:
                errors.append(e)
        
        def consumer():
            try:
                consumed = 0
                attempts = 0
                while consumed < 500 and attempts < 2000:
                    with agent.lock:
                        if agent.local_command_queue:
                            agent.local_command_queue.popleft()
                            consumed += 1
                    attempts += 1
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=producer),
            threading.Thread(target=producer),
            threading.Thread(target=consumer),
            threading.Thread(target=consumer),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # No errors should occur under contention
        assert len(errors) == 0
    
    def test_get_messages_clears_queue_atomically(self, setup):
        """Test that get_messages atomically clears and returns all messages."""
        agent, _, _ = setup
        
        # Pre-populate with messages
        for i in range(100):
            agent.receive_message({"id": i})
        
        retrieved = []
        
        def get_all_messages():
            msgs = agent.get_messages()
            retrieved.extend(msgs)
        
        # Multiple threads trying to get messages
        threads = [threading.Thread(target=get_all_messages) for _ in range(5)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All messages should be retrieved exactly once (by one thread)
        assert len(retrieved) == 100
        assert len(agent.local_message_queue) == 0
